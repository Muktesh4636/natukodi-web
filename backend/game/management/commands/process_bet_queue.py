import json
import logging
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
import redis
from django.conf import settings
from game.models import GameRound, Bet
from accounts.models import Wallet, Transaction, User

logger = logging.getLogger('game.bet_worker')

class Command(BaseCommand):
    help = 'Process bets from Redis queue and write to Database in batches'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Bet Queue Worker...'))
        
        # Setup Redis
        try:
            if hasattr(settings, 'REDIS_POOL') and settings.REDIS_POOL:
                redis_client = redis.Redis(connection_pool=settings.REDIS_POOL)
            else:
                redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    decode_responses=True
                )
            redis_client.ping()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Redis connection failed: {e}'))
            return

        batch_size = 50  # Process 50 bets at a time
        
        while True:
            try:
                # 1. Fetch a batch of bets from Redis
                # We use BLPOP to wait for items if the queue is empty (efficient)
                # But since we want batches, we'll use LRANGE and LTRIM or a loop
                
                bets_to_process = []
                # Try to get up to batch_size items
                for _ in range(batch_size):
                    # non-blocking pop
                    bet_json = redis_client.lpop('bet_queue')
                    if bet_json:
                        bets_to_process.append(json.loads(bet_json))
                    else:
                        break
                
                if not bets_to_process:
                    # Queue empty, sleep briefly
                    time.sleep(0.5)
                    continue

                self.stdout.write(f"Processing batch of {len(bets_to_process)} bets...")

                # 2. Process Batch in a single DB Transaction
                with transaction.atomic():
                    for bet_data in bets_to_process:
                        try:
                            user_id = bet_data['user_id']
                            round_id = bet_data['round_id']
                            number = bet_data['number']
                            chip_amount = Decimal(bet_data['chip_amount'])
                            
                            # Get Round and Wallet (select_for_update to be safe)
                            round_obj = GameRound.objects.get(round_id=round_id)
                            wallet = Wallet.objects.select_for_update().get(user_id=user_id)
                            
                            # Create Bet
                            Bet.objects.create(
                                user_id=user_id,
                                round=round_obj,
                                number=number,
                                chip_amount=chip_amount
                            )

                            # Update Wallet
                            balance_before = wallet.balance
                            wallet.balance -= chip_amount
                            wallet.save()
                            
                            # Create Transaction log
                            Transaction.objects.create(
                                user_id=user_id,
                                transaction_type='BET',
                                amount=chip_amount,
                                balance_before=balance_before,
                                balance_after=wallet.balance,
                                description=f"Bet on {number} in round {round_id} (Processed via Queue)"
                            )
                            
                            # Sync Redis balance with DB balance just in case of drift
                            # (Optional: only do this occasionally or if drift detected)
                            redis_client.set(f"user_balance:{user_id}", str(wallet.balance), ex=3600)

                        except Exception as bet_err:
                            logger.error(f"Error processing individual bet in batch: {bet_err}")
                            # In a real production system, you'd want a 'failed_bets' queue
                            continue

                self.stdout.write(self.style.SUCCESS(f"Successfully committed {len(bets_to_process)} bets to DB"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Worker Error: {e}"))
                time.sleep(2) # Wait before retry
