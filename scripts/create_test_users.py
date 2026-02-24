import os
import django
import random
import sys

# Setup Django environment - must run from backend/ so load_dotenv finds .env
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)  # Ensures same .env and db as Django server
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
django.setup()

from django.db.models import F
from django.contrib.auth.hashers import make_password
from accounts.models import User, Wallet
from decimal import Decimal

PASSWORD = "testpassword123"

def create_test_users(count=100):
    print(f"Creating {count} predictable test users for load testing...")
    for i in range(count):
        # Using a predictable name pattern: testuser_0, testuser_1, etc.
        username = f"testuser_{i}"
        phone = f"99999{i:05d}"
        
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(
                username=username,
                password=PASSWORD,
                phone_number=phone
            )
            # Give them starting balance
            wallet, _ = Wallet.objects.get_or_create(user=user)
            Wallet.objects.filter(user=user).update(balance=F('balance') + 5000)
            
            if (i + 1) % 10 == 0:
                print(f"Created {i + 1} users...")
        else:
            # If user exists, reset balance (password reset done in bulk below)
            user = User.objects.get(username=username)
            wallet, _ = Wallet.objects.get_or_create(user=user)
            Wallet.objects.filter(user=user).update(balance=5000)

    # Bulk reset passwords for all test users (fast)
    hashed = make_password(PASSWORD)
    User.objects.filter(username__startswith="testuser_").update(password=hashed)

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    create_test_users(count)
    print(f"Done! {count} users (testuser_0 to testuser_{count-1}) are ready with ₹5000 each.")
