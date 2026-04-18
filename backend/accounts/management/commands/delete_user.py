"""
Delete a user by username and clear common Redis keys for that user.

Usage:
  python manage.py delete_user <username>
  python manage.py delete_user <username> --force   # allow deleting superusers

Example:
  python manage.py delete_user 9182351381

This runs User.delete() (CASCADE removes wallet, bets, etc. per model rules).
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


def _purge_user_redis(user_id: int) -> None:
    try:
        from game.utils import get_redis_client

        r = get_redis_client()
        if not r:
            return
        keys = [
            f"user_balance:{user_id}",
            f"user_session:{user_id}",
            f"user_valid_iat:{user_id}",
            f"user_valid_refresh_jti:{user_id}",
            f"user_bets_stack:{user_id}",
        ]
        for k in keys:
            try:
                r.delete(k)
            except Exception:
                pass
    except Exception:
        pass


class Command(BaseCommand):
    help = "Delete a user by username (DB + Redis cache keys)."

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username to delete")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow deleting a superuser (dangerous).",
        )

    def handle(self, *args, **options):
        uname = (options["username"] or "").strip()
        force = options["force"]
        if not uname:
            raise CommandError("Username is required.")

        user = User.objects.filter(username__iexact=uname).first()
        if not user:
            raise CommandError(f'No user with username "{uname}".')

        if user.is_superuser and not force:
            raise CommandError(
                "Refusing to delete a superuser. Pass --force if you really mean it."
            )

        uid = user.id
        label = user.username
        _purge_user_redis(uid)
        user.delete()
        self.stdout.write(
            self.style.SUCCESS(f'Deleted user id={uid} username="{label}" (DB CASCADE + Redis cleanup).')
        )
