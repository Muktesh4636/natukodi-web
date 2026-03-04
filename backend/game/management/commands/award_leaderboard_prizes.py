from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Award daily leaderboard prizes to top 3 users (11 PM IST cutoff)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period-end-utc",
            dest="period_end_utc",
            default=None,
            help="Override period end time in UTC ISO format (e.g. 2026-02-26T17:30:00Z).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if current time is before 11 PM IST.",
        )

    def handle(self, *args, **options):
        import pytz
        from datetime import datetime, timedelta, time as dtime

        from accounts.models import Wallet, Transaction, User
        from game.models import LeaderboardSetting, LeaderboardPayout, UserDailyTurnover
        from game.utils import get_redis_client

        ist = pytz.timezone("Asia/Kolkata")

        # Determine period end (IST 23:00) and convert to UTC.
        override = options.get("period_end_utc")
        if override:
            # Accept Z or +00:00
            override_s = override.strip().replace("Z", "+00:00")
            period_end_utc = datetime.fromisoformat(override_s)
            if period_end_utc.tzinfo is None:
                period_end_utc = period_end_utc.replace(tzinfo=pytz.UTC)
        else:
            now_utc = timezone.now()
            now_ist = now_utc.astimezone(ist)

            target_end_ist = ist.localize(datetime.combine(now_ist.date(), dtime(23, 0)))
            if now_ist < target_end_ist and not options.get("force"):
                self.stdout.write(self.style.WARNING("Not yet 11 PM IST. Skipping (use --force to run)."))
                return
            if now_ist < target_end_ist:
                # Forced run before 11 PM: award the previous completed period.
                target_end_ist = target_end_ist - timedelta(days=1)

            period_end_utc = target_end_ist.astimezone(pytz.UTC)

        period_start_utc = period_end_utc - timedelta(days=1)
        period_date = period_start_utc.astimezone(ist).date()

        # Load prizes
        setting = LeaderboardSetting.objects.first()
        if not setting:
            setting = LeaderboardSetting.objects.create()

        prize_by_rank = {
            1: int(setting.prize_1st),
            2: int(setting.prize_2nd),
            3: int(setting.prize_3rd),
        }

        # Rank users by cached daily turnover for this period
        ranked = list(
            UserDailyTurnover.objects.filter(period_date=period_date, turnover__gt=0)
            .order_by("-turnover", "user_id")[:3]
            .values("user_id", "turnover")
        )

        if not ranked:
            self.stdout.write(self.style.WARNING("No eligible bets in period; nothing to award."))
            return

        redis_client = get_redis_client()

        awarded = 0
        skipped = 0

        for idx, row in enumerate(ranked, start=1):
            rank = idx
            amount = prize_by_rank.get(rank, 0)
            if amount <= 0:
                skipped += 1
                continue

            user_id = row["user_id"]

            try:
                with db_transaction.atomic():
                    # Idempotency: reserve this rank payout
                    payout = LeaderboardPayout.objects.create(
                        period_end=period_end_utc,
                        rank=rank,
                        user_id=user_id,
                        amount=amount,
                    )

                    wallet, _ = Wallet.objects.get_or_create(user_id=user_id)
                    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                    bal_before = int(wallet.balance)

                    # Prize behaves like bonus (adds to unavailable too)
                    wallet.add(amount, is_bonus=True)

                    tx = Transaction.objects.create(
                        user_id=user_id,
                        transaction_type="LEADERBOARD_PRIZE",
                        amount=amount,
                        balance_before=bal_before,
                        balance_after=int(wallet.balance),
                        description=f"Daily Leaderboard Prize (rank {rank}) for period ending {period_end_utc.isoformat()}",
                    )

                    payout.transaction_id = tx.id
                    payout.save(update_fields=["transaction_id"])

                    # Update Redis balance (best-effort)
                    try:
                        if redis_client:
                            redis_client.incrbyfloat(f"user_balance:{user_id}", float(amount))
                    except Exception:
                        pass

                awarded += 1
            except Exception as e:
                # If duplicate payout, ignore. If other error, bubble up.
                from django.db.utils import IntegrityError

                if isinstance(e, IntegrityError):
                    skipped += 1
                    continue
                raise

        self.stdout.write(
            self.style.SUCCESS(
                f"Awarded={awarded} skipped={skipped} period_start_utc={period_start_utc.isoformat()} period_end_utc={period_end_utc.isoformat()}"
            )
        )

