"""
backfill_journeys
=================
One-time command to create PlayerJourney + PlayerDailyState + Redis
player_state for every existing player who has deposited but doesn't
have a journey yet.

Usage:
    python manage.py backfill_journeys          # all eligible players
    python manage.py backfill_journeys --dry-run  # preview only, no writes
"""

import json
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max, Sum
from django.utils import timezone

from accounts.models import User, Wallet, Transaction, DepositRequest
from game.models import (
    PlayerJourney,
    PlayerDailyState,
    get_time_target,
)
from game.utils import get_redis_client

logger = logging.getLogger('backfill_journeys')


def _ist_today():
    try:
        import pytz
        return timezone.now().astimezone(pytz.timezone('Asia/Kolkata')).date()
    except Exception:
        return timezone.now().date()


class Command(BaseCommand):
    help = 'Backfill PlayerJourney and Redis player_state for existing players'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would happen without writing anything',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete all PlayerJourney, PlayerDailyState and Redis player_state:* (fresh start for all)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        do_reset = options['reset']
        redis_client = get_redis_client()

        if do_reset:
            self._do_reset(redis_client, dry_run)
            return

        if not redis_client and not dry_run:
            self.stderr.write(self.style.ERROR('Redis unavailable — aborting'))
            return

        today = _ist_today()

        already_have = set(
            PlayerJourney.objects.values_list('user_id', flat=True)
        )

        eligible_ids = set(
            DepositRequest.objects
            .filter(status='APPROVED')
            .values_list('user_id', flat=True)
            .distinct()
        )
        wallet_ids = set(
            Wallet.objects
            .filter(balance__gt=0)
            .values_list('user_id', flat=True)
        )
        eligible_ids |= wallet_ids

        to_backfill = eligible_ids - already_have

        self.stdout.write(
            f"Eligible: {len(eligible_ids)} | "
            f"Already have journey: {len(already_have)} | "
            f"To backfill: {len(to_backfill)}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes made'))
            return

        users = (
            User.objects
            .filter(id__in=to_backfill)
            .select_related('wallet')
        )

        created_count = 0
        skipped = 0
        errors = 0

        for user in users.iterator(chunk_size=200):
            try:
                first_deposit = (
                    DepositRequest.objects
                    .filter(user=user, status='APPROVED')
                    .aggregate(
                        first_date=Max('created_at'),
                        last_amount=Max('amount'),
                    )
                )
                first_date = first_deposit.get('first_date')
                deposit_amount = int(first_deposit.get('last_amount') or 0)

                if deposit_amount <= 0:
                    try:
                        deposit_amount = max(int(user.wallet.balance), 200)
                    except Exception:
                        deposit_amount = 200

                # Estimate active_days from first approved deposit date
                if first_date:
                    days_since = (timezone.now() - first_date).days
                    active_days = min(max(days_since, 1), 30)
                else:
                    active_days = 1

                journey = PlayerJourney.objects.create(
                    user=user,
                    active_days=active_days,
                    last_play_date=today,
                    first_deposit_date=(
                        first_date.date() if first_date else today
                    ),
                )
                journey.initialise_chart()

                day_type = journey.get_day_type(active_days)

                floor, emergency, target_min, target_max, budget = \
                    PlayerDailyState.compute_floor_and_target(
                        deposit_amount, day_type
                    )

                state, _ = PlayerDailyState.objects.update_or_create(
                    user=user,
                    date=today,
                    defaults={
                        'active_day_number': active_days,
                        'day_type': day_type,
                        'deposit_today': deposit_amount,
                        'floor_balance': floor,
                        'emergency_floor': emergency,
                        'target_min': target_min,
                        'target_max': target_max,
                        'daily_budget': budget,
                        'time_target_seconds': get_time_target(active_days),
                    },
                )

                # Push to Redis
                try:
                    current_balance = int(user.wallet.balance)
                except Exception:
                    current_balance = deposit_amount

                ps = {
                    'day_type': day_type,
                    'floor_balance': floor,
                    'emergency_floor': emergency,
                    'target_min': target_min,
                    'target_max': target_max,
                    'budget_remaining': budget,
                    'time_target_seconds': state.time_target_seconds,
                    'time_played_seconds': 0,
                    'time_target_reached': False,
                    'active_day': active_days,
                    'is_flagged': False,
                    'current_balance': current_balance,
                    'rounds_since_last_win': 0,
                }
                redis_client.set(
                    f"player_state:{user.id}",
                    json.dumps(ps),
                    ex=90000,
                )

                created_count += 1
                if created_count % 100 == 0:
                    self.stdout.write(f"  ... {created_count} done")

            except Exception as exc:
                errors += 1
                logger.error(f"Backfill failed for user {user.id}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {created_count} created, "
                f"{skipped} skipped, {errors} errors"
            )
        )
        logger.info(
            f"backfill_journeys: {created_count} created, "
            f"{skipped} skipped, {errors} errors"
        )

    def _do_reset(self, redis_client, dry_run):
        """Delete all journey/daily state and Redis player_state keys."""
        journey_count = PlayerJourney.objects.count()
        daily_count = PlayerDailyState.objects.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN — would delete {journey_count} PlayerJourney, '
                    f'{daily_count} PlayerDailyState, and all player_state:* in Redis'
                )
            )
            if redis_client:
                keys = redis_client.keys('player_state:*')
                self.stdout.write(f'  Redis keys to delete: {len(keys)}')
            return

        if not redis_client:
            self.stderr.write(self.style.ERROR('Redis unavailable — cannot clear player_state keys'))
            return

        deleted_journeys, _ = PlayerJourney.objects.all().delete()
        deleted_daily, _ = PlayerDailyState.objects.all().delete()

        keys = redis_client.keys('player_state:*')
        deleted_redis = 0
        if keys:
            deleted_redis = redis_client.delete(*keys)

        self.stdout.write(
            self.style.SUCCESS(
                f'Reset complete: {deleted_journeys} PlayerJourney, '
                f'{deleted_daily} PlayerDailyState, {deleted_redis} Redis keys removed'
            )
        )
        logger.info(
            f"backfill_journeys --reset: journeys={deleted_journeys} "
            f"daily_states={deleted_daily} redis_keys={deleted_redis}"
        )
