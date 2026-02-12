import os
import django
import random
import sys

# Setup Django environment
sys.path.insert(0, os.path.abspath('./backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
django.setup()

from accounts.models import User, Wallet
from decimal import Decimal

def create_test_users(count=100):
    print(f"Creating {count} predictable test users for load testing...")
    for i in range(count):
        # Using a predictable name pattern: testuser_0, testuser_1, etc.
        username = f"testuser_{i}"
        phone = f"99999{i:05d}"
        
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(
                username=username,
                password="testpassword123",
                phone_number=phone
            )
            # Give them starting balance
            wallet, _ = Wallet.objects.get_or_create(user=user)
            wallet.balance = Decimal('5000.00')
            wallet.save()
            
            if (i + 1) % 10 == 0:
                print(f"Created {i + 1} users...")
        else:
            # If user exists, just reset their balance
            user = User.objects.get(username=username)
            wallet, _ = Wallet.objects.get_or_create(user=user)
            wallet.balance = Decimal('5000.00')
            wallet.save()

if __name__ == "__main__":
    create_test_users(300)
    print("Done! 300 users (testuser_0 to testuser_299) are ready with ₹5000 each.")
