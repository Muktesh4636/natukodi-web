"""
Log out all users everywhere:
- App (JWT): set Redis key so all tokens issued before now are rejected.
- Game admin (Django sessions): clear the session table.

Usage:
  python manage.py logout_all_sessions
"""
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.sessions.models import Session


def _get_redis():
    if getattr(settings, 'REDIS_POOL', None):
        import redis
        return redis.Redis(connection_pool=settings.REDIS_POOL)
    return None


class Command(BaseCommand):
    help = 'Log out all users: invalidate all JWT tokens (app) and clear all Django sessions (game-admin).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-sessions',
            action='store_true',
            help='Only invalidate JWT (app); do not clear game-admin sessions.',
        )
        parser.add_argument(
            '--no-jwt',
            action='store_true',
            help='Only clear game-admin sessions; do not invalidate JWT.',
        )

    def handle(self, *args, **options):
        now = int(time.time())
        r = _get_redis()

        # 1. Invalidate all JWT tokens (app users)
        if not options['no_jwt']:
            if r:
                key = 'logout_all_issued_before'
                r.set(key, str(now))
                self.stdout.write(self.style.SUCCESS(f'All app (JWT) sessions invalidated. Set Redis {key} = {now}'))
            else:
                self.stdout.write(self.style.ERROR('Redis not available. JWT invalidation skipped.'))

        # 2. Clear Django sessions (game-admin users)
        if not options['no_sessions']:
            count, _ = Session.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Cleared {count} game-admin session(s).'))

        # 3. Optional: clear Redis user_session cache so next login is fresh
        if r and not options['no_jwt']:
            try:
                keys = list(r.scan_iter('user_session:*', count=1000))
                if keys:
                    r.delete(*keys)
                    self.stdout.write(self.style.SUCCESS(f'Cleared {len(keys)} Redis user_session cache key(s).'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Could not clear user_session keys: {e}'))

        self.stdout.write('Done. All users must log in again.')
