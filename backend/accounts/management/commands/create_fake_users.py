from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from accounts.models import Wallet
from faker import Faker
import random
from django.db import transaction

User = get_user_model()

class Command(BaseCommand):
    help = 'Create fake users and their wallets'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=10, help='Number of users to create')

    def handle(self, *args, **kwargs):
        count = kwargs['count']
        fake = Faker('en_IN')
        
        batch_size = 1000
        created_count = 0
        
        hashed_password = make_password('password123')
        
        self.stdout.write(f'Starting creation of {count} users with pre-hashed password...')

        for i in range(0, count, batch_size):
            current_batch_size = min(batch_size, count - i)
            users_to_create = []
            
            # Pre-generate data to minimize collision risk
            for _ in range(current_batch_size):
                # Ensure unique username by appending random digits
                username = f"{fake.user_name()}_{random.randint(100000, 999999)}"
                email = fake.email()
                
                # Phone number: +91 + 10 digits
                phone_number = f"+91{random.randint(6000000000, 9999999999)}"
                
                user = User(
                    username=username,
                    email=email,
                    phone_number=phone_number,
                    password=hashed_password,  # Set pre-hashed password directly
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    is_active=True,
                    gender=random.choice(['MALE', 'FEMALE', 'OTHER']),
                    address=fake.address().replace('\n', ', ')
                )
                users_to_create.append(user)
            
            try:
                with transaction.atomic():
                    # Create users
                    created_users = User.objects.bulk_create(users_to_create)
                    
                    # Create wallets for the created users
                    wallets_to_create = []
                    for user in created_users:
                        if user.pk:  # Ensure user was saved and has an ID
                            wallets_to_create.append(Wallet(user=user, balance=0))
                    
                    Wallet.objects.bulk_create(wallets_to_create)
                    
                    created_count += len(created_users)
                    self.stdout.write(f'Created {created_count}/{count} users and wallets')
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error creating batch starting at {i}: {e}'))
                # If a batch fails, we could retry or just skip. 
                # For this task, skipping or stopping is acceptable, but let's try to continue or debug.
                # Since we used random unique suffixes, collisions should be rare.
                continue

        self.stdout.write(self.style.SUCCESS(f'Successfully created {created_count} users.'))
