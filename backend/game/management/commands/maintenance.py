"""
Toggle maintenance mode via Redis (no restart needed).
Maintenance auto-disables after the set duration (Redis TTL).

Usage:
  python manage.py maintenance on              # Enable for 8 hours, then auto-disable
  python manage.py maintenance on --minutes 30
  python manage.py maintenance off
  python manage.py maintenance status
"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings


def _get_redis():
    """Get Redis client from settings pool."""
    if getattr(settings, 'REDIS_POOL', None):
        import redis
        return redis.Redis(connection_pool=settings.REDIS_POOL)
    return None


class Command(BaseCommand):
    help = 'Toggle maintenance mode. App and APK download are blocked during maintenance.'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['on', 'off', 'status'],
            help='on=enable, off=disable, status=show current state',
        )
        parser.add_argument(
            '--minutes',
            type=int,
            default=480,
            metavar='N',
            help='When using "on": auto-disable after N minutes (default: 480 = 8 hours).',
        )

    def handle(self, *args, **options):
        action = options['action']
        r = _get_redis()

        if action == 'on':
            if r:
                mins = options.get('minutes', 480)
                if mins < 1:
                    mins = 480
                import time
                now = int(time.time())
                until = now + (mins * 60)
                r.set('maintenance_mode', '1')
                r.set('maintenance_until', str(until))
                r.expireat('maintenance_mode', until)
                r.expireat('maintenance_until', until)
                self.stdout.write(self.style.SUCCESS(f'Maintenance ENABLED for {mins} minutes. It will auto-disable after that.'))
            else:
                self.stdout.write(self.style.ERROR('Redis not configured. Set MAINTENANCE_MODE=1 in env instead.'))
        elif action == 'off':
            if r:
                r.delete('maintenance_mode')
                self.stdout.write(self.style.SUCCESS('Maintenance mode DISABLED.'))
            else:
                self.stdout.write(self.style.ERROR('Redis not configured. Unset MAINTENANCE_MODE in env.'))
        else:  # status
            redis_val = r.get('maintenance_mode') if r else None
            env_val = os.getenv('MAINTENANCE_MODE', '0')
            self.stdout.write(f'Redis maintenance_mode: {"ON" if redis_val else "OFF"}')
            self.stdout.write(f'MAINTENANCE_MODE env: {env_val}')
            if redis_val or env_val.lower() in ('1', 'true', 'yes'):
                self.stdout.write(self.style.WARNING('Maintenance is ACTIVE'))
            else:
                self.stdout.write('Maintenance is inactive')
