"""
Set password for an admin (staff) user. Use when the web "Change password" form
didn't persist or you need to reset login credentials.

Usage:
  python manage.py set_admin_password <username> <new_password>

Example:
  python manage.py set_admin_password sai sai123
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Set password for an admin user (for game-admin login)."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username of the admin (e.g. sai)')
        parser.add_argument('password', type=str, help='New password to set')

    def handle(self, *args, **options):
        username = (options['username'] or '').strip()
        password = (options['password'] or '').strip()
        if not username:
            raise CommandError('Username is required.')
        if not password:
            raise CommandError('Password is required.')
        if len(password) < 4:
            raise CommandError('Password must be at least 4 characters.')

        user = User.objects.filter(username__iexact=username).first()
        if not user:
            raise CommandError(f'User with username "{username}" not found.')
        if not (user.is_staff or user.is_superuser):
            raise CommandError(f'User "{username}" is not an admin (is_staff=False). Use this command only for admin users.')

        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Password updated for "{user.username}". You can now login with username="{user.username}" and the new password.'))
