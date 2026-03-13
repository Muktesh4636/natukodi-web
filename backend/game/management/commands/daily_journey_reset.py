"""
daily_journey_reset
===================
Runs at midnight IST. For every player who played today:
  - Pushes fresh player_state to Redis with next day's config.

Run via cron:
  30 18 * * * /path/to/venv/bin/python manage.py daily_journey_reset
  (18:30 UTC = 00:00 IST)
"""

import json
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from game.models import PlayerJourney, PlayerDailyState, get_time_target
from game.utils import get_redis_client

logger = logging.getLogger('daily_journey_reset')


class Command(BaseCommand):
    help = 'Reset daily player journey states at midnight IST'

    def handle(self, *args, **options):
        redis_client = get_redis_client()
        if not redis_client:
            self.stderr.write('Redis unavailable — aborting daily reset')
            return

        try:
            import pytz
            IST = pytz.timezone('Asia/Kolkata')
            today = timezone.now().astimezone(IST).date()
        except Exception:
            today = timezone.now().date()

        journeys = PlayerJourney.objects.select_related('user__wallet').all()
        updated = 0
        skipped = 0
        errors = 0

        for journey in journeys:
            try:
                if journey.active_days >= 30:
                    # Journey complete — clear algorithm state; player gets pure random
                    ps_key = f"player_state:{journey.user_id}"
                    redis_client.delete(ps_key)
                    skipped += 1
                    continue

                user = journey.user
                active_day = journey.active_days + 1  # next day
                day_type = journey.get_day_type(active_day)

                # Estimate deposit from last daily state
                last_state = (
                    PlayerDailyState.objects
                    .filter(user=user)
                    .order_by('-date')
                    .first()
                )
                deposit_est = last_state.deposit_today if last_state else 0

                floor, emergency, target_min, target_max, budget = \
                    PlayerDailyState.compute_floor_and_target(deposit_est, day_type)

                try:
                    current_balance = int(user.wallet.balance)
                except Exception:
                    current_balance = 0

                ps_key = f"player_state:{user.id}"
                existing_raw = redis_client.get(ps_key) or '{}'
                try:
                    existing = json.loads(existing_raw)
                except Exception:
                    existing = {}

                existing.update({
                    'day_type': day_type,
                    'floor_balance': floor,
                    'emergency_floor': emergency,
                    'target_min': target_min,
                    'target_max': target_max,
                    'budget_remaining': budget,
                    'time_target_seconds': get_time_target(active_day),
                    'time_played_seconds': 0,
                    'time_target_reached': False,
                    'active_day': active_day,
                    'is_flagged': journey.is_flagged,
                    'current_balance': current_balance,
                    'rounds_since_last_win': 0,
                })
                redis_client.set(ps_key, json.dumps(existing), ex=90000)  # 25 hours
                updated += 1

            except Exception as exc:
                errors += 1
                logger.error(f"Reset failed for user {journey.user_id}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f'Daily reset complete: {updated} players updated, {skipped} skipped (journey complete), {errors} errors'
            )
        )
        logger.info(f'Daily reset: {updated} updated, {skipped} skipped, {errors} errors')
