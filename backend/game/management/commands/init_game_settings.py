"""
Management command to initialize default game settings in the database.
Run this once to set up default timing values that can be configured via admin panel.
"""
from django.core.management.base import BaseCommand
from game.models import GameSettings
from django.conf import settings


class Command(BaseCommand):
    help = 'Initialize default game settings in the database'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Initializing game settings...'))
        
        # Default settings from settings.py
        default_settings = getattr(settings, 'GAME_SETTINGS', {})
        
        # Define settings to initialize with descriptions
        settings_to_init = [
            {
                'key': 'BETTING_CLOSE_TIME',
                'value': str(default_settings.get('BETTING_CLOSE_TIME', 30)),
                'description': 'Time in seconds when betting closes (default: 30)'
            },
            {
                'key': 'DICE_RESULT_TIME',
                'value': str(default_settings.get('DICE_RESULT_TIME', 51)),
                'description': 'Time in seconds when dice result is announced (default: 51)'
            },
            {
                'key': 'ROUND_END_TIME',
                'value': str(default_settings.get('ROUND_END_TIME', 80)),
                'description': 'Total round duration in seconds (default: 80)'
            },
            {'key': 'MAX_BET', 'value': '50000', 'description': 'Maximum bet amount per number'},
            {'key': 'APP_VERSION_CODE', 'value': '1', 'description': 'Version code of latest APK. Bump when releasing new APK.'},
            {'key': 'APP_VERSION_NAME', 'value': '1.0', 'description': 'Display version name shown in update dialog.'},
            {'key': 'APP_DOWNLOAD_URL', 'value': '/api/download/apk/', 'description': 'Direct URL to download the latest APK.'},
            {'key': 'APP_FORCE_UPDATE', 'value': 'false', 'description': 'If true, users must update to continue using the app.'},
        ]
        
        created_count = 0
        updated_count = 0
        
        for setting_data in settings_to_init:
            setting, created = GameSettings.objects.update_or_create(
                key=setting_data['key'],
                defaults={
                    'value': setting_data['value'],
                    'description': setting_data['description']
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Created setting: {setting.key} = {setting.value}'
                    )
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'↻ Updated setting: {setting.key} = {setting.value}'
                    )
                )
        
        self.stdout.write(self.style.SUCCESS(
            f'\nCompleted! Created {created_count} new settings, updated {updated_count} existing settings.'
        ))
        self.stdout.write(
            self.style.SUCCESS(
                'You can now configure these settings in the Django admin panel at /admin/game/gamesettings/'
            )
        )







