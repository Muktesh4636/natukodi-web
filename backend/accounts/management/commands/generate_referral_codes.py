from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Generate unique referral codes for users who do not have one'

    def handle(self, *args, **options):
        users_without_codes = User.objects.filter(referral_code__isnull=True) | User.objects.filter(referral_code='')
        count = users_without_codes.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('All users already have referral codes.'))
            return
        
        self.stdout.write(f'Found {count} users without referral codes. Generating codes...')
        
        updated = 0
        for user in users_without_codes:
            try:
                # Generate unique referral code using the model method
                user.referral_code = user.generate_unique_referral_code()
                user.save()
                updated += 1
                self.stdout.write(f'Generated referral code for user: {user.username} - {user.referral_code}')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error generating code for {user.username}: {str(e)}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully generated referral codes for {updated} users.')
        )
