from django.core.management.base import BaseCommand
from accounts.models import User
import random

class Command(BaseCommand):
    help = 'Update existing referral codes to new GunduataXXX format'

    def handle(self, *args, **options):
        self.stdout.write('Updating existing referral codes to GunduataXXX format...')

        # Get users with old format referral codes (not starting with Gunduata)
        users_to_update = User.objects.filter(
            referral_code__isnull=False
        ).exclude(referral_code__istartswith='Gunduata')

        total_updated = 0
        for user in users_to_update:
            old_code = user.referral_code
            user.referral_code = user.generate_unique_referral_code()
            user.save(update_fields=['referral_code'])
            self.stdout.write(f'Updated {user.username}: {old_code} → {user.referral_code}')
            total_updated += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully updated {total_updated} referral codes'))

        # Show sample of new codes
        sample_users = User.objects.filter(referral_code__istartswith='Gunduata')[:5]
        self.stdout.write('\nSample of new GunduataXXX codes:')
        for user in sample_users:
            self.stdout.write(f'{user.username}: {user.referral_code}')