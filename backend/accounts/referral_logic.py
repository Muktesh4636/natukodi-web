"""
Referral rewards:

1. **Instant bonus**: referrer gets ``REFERRAL_INSTANT_BONUS_PER_REFEREE`` (default ₹100) once when a
   referee's **first** deposit is approved (API + game-admin flows).

2. **Daily commission**: referees' net wallet loss per IST calendar day × **tiered %** by referrer's
   **lifetime referral count** (see ``REFERRAL_COMMISSION_SLABS``). Run
   ``manage.py process_referral_daily_commission`` daily at ~01:00 Asia/Kolkata.

Override instant bonus via ``GameSettings`` key ``REFERRAL_INSTANT_BONUS_PER_REFEREE``.
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

# Lifetime referrals (signups with referred_by = referrer) → daily-loss commission rate
REFERRAL_COMMISSION_SLABS = (
    (1, 10, Decimal('0.02')),
    (11, 30, Decimal('0.03')),
    (31, 50, Decimal('0.04')),
    (51, 100, Decimal('0.06')),
    (101, 250, Decimal('0.08')),
)


def referral_per_referee_bonus_amount() -> int:
    """Rupees credited to referrer when a referee's first deposit is approved."""
    try:
        from game.utils import get_game_setting

        raw = get_game_setting('REFERRAL_INSTANT_BONUS_PER_REFEREE', 100)
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 100


def referral_commission_rate_for_count(total_referrals: int) -> Decimal:
    """
    Daily-loss commission rate from lifetime referral count (tiers).
    251+ referrals stay at top slab (8%).
    """
    n = int(total_referrals or 0)
    if n <= 0:
        return Decimal('0')
    if n > 250:
        return Decimal('0.08')
    for lo, hi, rate in REFERRAL_COMMISSION_SLABS:
        if lo <= n <= hi:
            return rate
    return Decimal('0.08')


def commission_slabs_for_api():
    """Tier table for GET /api/auth/referral-data/ (``commission_slabs``)."""
    out = []
    for lo, hi, rate in REFERRAL_COMMISSION_SLABS:
        out.append({
            'min_referrals': lo,
            'max_referrals': hi,
            'commission_percent': float(rate * 100),
        })
    out.append({
        'min_referrals': 251,
        'max_referrals': None,
        'commission_percent': 8.0,
    })
    return out


def award_referrer_instant_bonus_on_referee_first_deposit(deposit_request):
    """
    Credit referrer REFERRAL_BONUS when referee's first deposit is approved (once per referee).

    Caller must already hold an outer atomic block; deposit row must be APPROVED and saved.
    """
    from .models import DepositRequest, Wallet, Transaction

    referee = deposit_request.user
    referrer = getattr(referee, 'referred_by', None)
    if not referrer or referrer.is_staff or referrer.is_superuser:
        return False

    if DepositRequest.objects.filter(user_id=referee.id, status='APPROVED').exclude(pk=deposit_request.pk).exists():
        return False

    bonus = referral_per_referee_bonus_amount()
    if bonus <= 0:
        return False

    rw, _ = Wallet.objects.select_for_update().get_or_create(user_id=referrer.id)
    rb_before = rw.balance
    rw.add(bonus, is_bonus=True)
    Wallet.objects.filter(pk=rw.pk).update(total_deposits=F('total_deposits') + int(bonus))
    rw.refresh_from_db()
    Wallet.apply_deposit_rotation_credit(rw.pk, int(bonus))
    Transaction.objects.create(
        user_id=referrer.id,
        transaction_type='REFERRAL_BONUS',
        amount=bonus,
        balance_before=rb_before,
        balance_after=rw.balance,
        description=(
            f'Referral instant bonus ₹{bonus} — first deposit approved for referee '
            f'{referee.username} (deposit #{deposit_request.pk})'
        ),
    )
    try:
        from game.utils import get_redis_client

        r = get_redis_client()
        if r:
            r.incrbyfloat(f'user_balance:{referrer.id}', float(bonus))
    except Exception as exc:
        logger.warning('Redis sync failed after referral instant bonus referrer=%s: %s', referrer.id, exc)

    logger.info(
        'Referral instant bonus ₹%s → referrer=%s referee=%s deposit=%s',
        bonus,
        referrer.username,
        referee.username,
        deposit_request.pk,
    )
    return True


def local_day_bounds(target_date: date):
    """Start (inclusive) and end (exclusive) of calendar day in configured TIME_ZONE."""
    tz = ZoneInfo(str(settings.TIME_ZONE))
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def wallet_balance_immediately_before(user_id: int, dt_aware) -> int:
    """
    Wallet balance just before ``dt_aware``: balance_after of last Transaction strictly before dt.
    If none, 0.
    """
    from .models import Transaction

    row = (
        Transaction.objects.filter(user_id=user_id, created_at__lt=dt_aware)
        .order_by('-created_at')
        .values_list('balance_after', flat=True)
        .first()
    )
    return int(row) if row is not None else 0


def yesterday_local_date() -> date:
    tz = ZoneInfo(str(settings.TIME_ZONE))
    now_local = timezone.now().astimezone(tz)
    return (now_local.date() - timedelta(days=1))


def process_referral_daily_commissions_for_date(target_date: date, *, dry_run: bool = False) -> dict:
    """
    For each referred user, compute net wallet loss on ``target_date`` (IST midnight boundaries).
    Credit referrer ``tier_rate × loss`` where tier follows referrer's ``total_referrals_count``.

    Idempotent via ReferralDailyCommission unique(referee, commission_date).
    """
    from django.contrib.auth import get_user_model

    from .models import ReferralDailyCommission, Transaction, Wallet

    User = get_user_model()

    day_start, day_end = local_day_bounds(target_date)

    stats = {
        'target_date': str(target_date),
        'dry_run': dry_run,
        'referees_seen': 0,
        'skipped_staff_referee': 0,
        'skipped_no_referrer': 0,
        'skipped_already_processed': 0,
        'skipped_no_loss': 0,
        'skipped_staff_referrer': 0,
        'skipped_zero_rate': 0,
        'skipped_zero_commission': 0,
        'credits_created': 0,
        'total_commission_amount': 0,
    }

    qs = User.objects.filter(referred_by_id__isnull=False).select_related('referred_by').iterator(chunk_size=300)

    for referee in qs:
        stats['referees_seen'] += 1

        if referee.is_staff or referee.is_superuser:
            stats['skipped_staff_referee'] += 1
            continue

        referrer = referee.referred_by
        if not referrer:
            stats['skipped_no_referrer'] += 1
            continue

        if ReferralDailyCommission.objects.filter(referee_id=referee.id, commission_date=target_date).exists():
            stats['skipped_already_processed'] += 1
            continue

        open_bal = wallet_balance_immediately_before(referee.id, day_start)
        close_bal = wallet_balance_immediately_before(referee.id, day_end)
        loss = max(0, open_bal - close_bal)

        if loss <= 0:
            stats['skipped_no_loss'] += 1
            continue

        ref_user = User.objects.filter(pk=referrer.id).only(
            'id', 'is_staff', 'is_superuser', 'username', 'total_referrals_count'
        ).first()
        if not ref_user or ref_user.is_staff or ref_user.is_superuser:
            stats['skipped_staff_referrer'] += 1
            continue

        n = int(ref_user.total_referrals_count or 0)
        rate = referral_commission_rate_for_count(n)
        if rate <= 0:
            stats['skipped_zero_rate'] += 1
            continue

        commission = int(Decimal(loss) * rate)
        if commission <= 0:
            stats['skipped_zero_commission'] += 1
            continue

        stats['total_commission_amount'] += commission

        if dry_run:
            stats['credits_created'] += 1
            continue

        desc = (
            f'Referral commission {float(rate * 100):g}% on referee {referee.username} '
            f'daily loss ₹{loss} ({target_date})'
        )

        with transaction.atomic():
            ref_wallet, _ = Wallet.objects.select_for_update().get_or_create(user_id=ref_user.id)
            rb_before = ref_wallet.balance
            ref_wallet.add(commission, is_bonus=True)
            Wallet.objects.filter(pk=ref_wallet.pk).update(total_deposits=F('total_deposits') + int(commission))
            ref_wallet.refresh_from_db()
            Wallet.apply_deposit_rotation_credit(ref_wallet.pk, int(commission))

            tx = Transaction.objects.create(
                user_id=ref_user.id,
                transaction_type='REFERRAL_COMMISSION',
                amount=commission,
                balance_before=rb_before,
                balance_after=ref_wallet.balance,
                description=desc,
            )
            ReferralDailyCommission.objects.create(
                referrer_id=ref_user.id,
                referee_id=referee.id,
                commission_date=target_date,
                opening_balance=open_bal,
                closing_balance=close_bal,
                loss_amount=loss,
                commission_rate=rate,
                commission_amount=commission,
                transaction=tx,
            )

        try:
            from game.utils import get_redis_client

            r = get_redis_client()
            if r:
                r.incrbyfloat(f'user_balance:{ref_user.id}', float(commission))
        except Exception as e:
            logger.warning('Redis sync failed after referral commission uid=%s: %s', ref_user.id, e)

        stats['credits_created'] += 1
        logger.info(
            'Referral commission ₹%s → %s (%.2f%%) loss ₹%s referee=%s date=%s',
            commission,
            ref_user.username,
            float(rate * 100),
            loss,
            referee.username,
            target_date,
        )

    return stats
