"""
Rename a user's login username (e.g. phone number -> display name).

Usage:
  python manage.py rename_user <old_username> <new_username>

Example:
  python manage.py rename_user 9182351381 mahesh

Updates Redis user_session cache username if present so JWT/cache stay consistent.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Change a user's username field."

    def add_arguments(self, parser):
        parser.add_argument("old_username", type=str, help="Current username")
        parser.add_argument("new_username", type=str, help="New username")

    def handle(self, *args, **options):
        old = (options["old_username"] or "").strip()
        new = (options["new_username"] or "").strip()
        if not old or not new:
            raise CommandError("Both old and new usernames are required.")
        if old == new:
            raise CommandError("Old and new usernames are the same; nothing to do.")

        user = User.objects.filter(username__iexact=old).first()
        if not user:
            raise CommandError(f'No user with username "{old}".')

        if User.objects.filter(username__iexact=new).exclude(pk=user.pk).exists():
            raise CommandError(f'Username "{new}" is already taken by another user.')

        user.username = new
        user.save(update_fields=["username", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f'Updated user id={user.pk}: "{old}" -> "{new}".'))

        try:
            from game.utils import get_redis_client

            r = get_redis_client()
            if r:
                key = f"user_session:{user.id}"
                raw = r.get(key)
                if raw:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="ignore")
                    data = json.loads(raw)
                    data["username"] = new
                    data["id"] = user.id
                    r.set(key, json.dumps(data), ex=3600)
                    self.stdout.write(f"  Redis {key} username refreshed.")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Redis session cache not updated (non-fatal): {e}"))
