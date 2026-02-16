"""
Management command to sync Redis wallet balances to Database.

This command reconciles Redis balances (real-time ledger) with DB wallet table.
Should be run periodically (e.g., every 5-10 minutes) via cron or scheduler.

Architecture: Redis is the real-time ledger, DB is eventually consistent.
"""
import logging
import redis
from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import Wallet
from decimal import Decimal

logger = logging.getLogger('game.reconciliation')

class Command(BaseCommand):
    help = 'Sync Redis wallet balances to Database (reconciliation job)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually updating DB',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync only specific user ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id_filter = options.get('user_id')
        
        self.stdout.write(self.style.SUCCESS('Starting Redis → DB Balance Reconciliation...'))
        
        # Connect to Redis
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD if hasattr(settings, 'REDIS_PASSWORD') else None,
                decode_responses=True,
                socket_connect_timeout=5
            )
            redis_client.ping()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Redis connection failed: {e}'))
            return

        # Get all Redis balance keys
        balance_pattern = 'user_balance:*'
        if user_id_filter:
            balance_pattern = f'user_balance:{user_id_filter}'
        
        try:
            # Scan for all balance keys (handles large datasets)
            balance_keys = []
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=balance_pattern, count=1000)
                balance_keys.extend(keys)
                if cursor == 0:
                    break
            
            if not balance_keys:
                self.stdout.write(self.style.WARNING('No Redis balance keys found'))
                return
            
            self.stdout.write(f'Found {len(balance_keys)} Redis balance keys')
            
            synced_count = 0
            error_count = 0
            total_diff = Decimal('0')
            
            for balance_key in balance_keys:
                try:
                    # Extract user_id from key: "user_balance:123"
                    user_id = int(balance_key.split(':')[1])
                    
                    # Get Redis balance
                    redis_balance_str = redis_client.get(balance_key)
                    if redis_balance_str is None:
                        continue  # Key expired or deleted
                    
                    redis_balance = Decimal(redis_balance_str)
                    
                    # Get DB wallet
                    try:
                        wallet = Wallet.objects.get(user_id=user_id)
                        db_balance = wallet.balance
                    except Wallet.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f'⚠️  Wallet not found for user {user_id}, skipping'))
                        error_count += 1
                        continue
                    
                    # Compare balances
                    diff = redis_balance - db_balance
                    
                    if abs(diff) > Decimal('0.01'):  # Only sync if difference > 1 paisa
                        self.stdout.write(
                            f'  User {user_id}: Redis={redis_balance:.2f}, DB={db_balance:.2f}, '
                            f'Diff={diff:+.2f}'
                        )
                        
                        if not dry_run:
                            # Update DB balance to match Redis
                            wallet.balance = redis_balance
                            wallet.save(update_fields=['balance'])
                            synced_count += 1
                            total_diff += abs(diff)
                        else:
                            synced_count += 1
                            total_diff += abs(diff)
                    else:
                        # Balances match (within 1 paisa tolerance)
                        pass
                        
                except ValueError as e:
                    self.stdout.write(self.style.WARNING(f'⚠️  Invalid balance key format: {balance_key}'))
                    error_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Error syncing {balance_key}: {e}'))
                    error_count += 1
                    logger.error(f'Error syncing balance for {balance_key}: {e}', exc_info=True)
            
            # Summary
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('=' * 60))
            if dry_run:
                self.stdout.write(self.style.SUCCESS(f'✅ DRY RUN: Would sync {synced_count} wallets'))
            else:
                self.stdout.write(self.style.SUCCESS(f'✅ Synced {synced_count} wallets'))
            self.stdout.write(f'   Total difference reconciled: ₹{total_diff:.2f}')
            if error_count > 0:
                self.stdout.write(self.style.WARNING(f'⚠️  Errors: {error_count}'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Reconciliation failed: {e}'))
            logger.error(f'Reconciliation job failed: {e}', exc_info=True)
