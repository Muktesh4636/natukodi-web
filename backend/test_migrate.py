import os
import sys
import django
from django.conf import settings

# Setup Django environment
sys.path.append('/Users/pradyumna/apk_of_ata/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
django.setup()

from django.db import connection

print(f"Current database engine: {settings.DATABASES['default']['ENGINE']}")
print(f"Current database host: {settings.DATABASES['default'].get('HOST')}")

# Try to run migrations
from django.core.management import call_command

try:
    print("Running migrations...")
    call_command('migrate', 'accounts')
    print("Migrations completed successfully.")
except Exception as e:
    print(f"Error running migrations: {e}")
