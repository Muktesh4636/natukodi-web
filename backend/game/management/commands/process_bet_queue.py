import json
import logging
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
import redis
from django.conf import settings
from game.models import GameRound, Bet, DiceResult
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
                redis_kwargs = {
                    'host': settings.REDIS_HOST,
                    'port': settings.REDIS_PORT,
                    'db': settings.REDIS_DB,
                    'decode_responses': True,
                    'socket_connect_timeout': 5,
                    'socket_timeout': 5,
                }
                if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
                    redis_kwargs['password'] = settings.REDIS_PASSWORD
                redis_client = redis.Redis(**redis_kwargs)
            redis_client.ping()
            self.stdout.write(self.style.SUCCESS('✅ Redis connected successfully'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Redis connection failed: {e}'))
            import traceback
            traceback.print_exc()
            return

        batch_size = 50  # Process 50 bets at a time
        STREAM_NAME = "round_events_stream"
        
        # Ensure stream exists or handle if it doesn't
        last_id = '$'  # Start from new messages
        try:
            # Try to get the last ID from the stream to avoid missing events on restart
            # For simplicity, we'll start from the end, but in production, you'd save last_id
            pass
        except:
            pass

        while True:
            try:
                # 1. Process Game Events (Round Start/End) from Redis Stream
                # We check for events first as they are critical for round creation
                events = redis_client.xread({STREAM_NAME: '0'}, count=10, block=100)
                if events:
                    for stream, messages in events:
                        for message_id, data in messages:
                            event_type = data.get('type')
                            round_id = data.get('round_id')
                            
                            try:
                                with transaction.atomic():
                                    if event_type == 'round_start':
                                        start_time_str = data.get('start_time')
                                        durations = json.loads(data.get('durations', '{}'))
                                        
                                        # Create GameRound in DB
                                        GameRound.objects.get_or_create(
                                            round_id=round_id,
                                            defaults={
                                                'status': 'BETTING',
                                                'start_time': start_time_str,
                                                'betting_close_seconds': durations.get('betting_close_time', 30),
                                                'dice_roll_seconds': durations.get('dice_roll_time', 35),
                                                'dice_result_seconds': durations.get('dice_result_time', 45),
                                                'round_end_seconds': durations.get('round_end_time', 70)
                                            }
                                        )
                                        self.stdout.write(self.style.SUCCESS(f"Created Round {round_id} in DB"))
                                    
                                    elif event_type == 'round_result':
                                        result = data.get('result')
                                        dice_values = json.loads(data.get('dice_values', '[]'))
                                        end_time_str = data.get('end_time')
                                        
                                        # Update GameRound and calculate payouts
                                        round_obj = GameRound.objects.get(round_id=round_id)
                                        round_obj.status = 'RESULT'
                                        round_obj.dice_result = result
                                        round_obj.result_time = end_time_str
                                        
                                        # Set individual dice values
                                        if len(dice_values) == 6:
                                            for i, val in enumerate(dice_values, 1):
                                                setattr(round_obj, f'dice_{i}', val)
                                        
                                        round_obj.save()
                                        
                                        # Create DiceResult record
                                        DiceResult.objects.update_or_create(
                                            round=round_obj,
                                            defaults={'result': result}
                                        )
                                        
                                        # Calculate Payouts
                                        from game.views import calculate_payouts
                                        calculate_payouts(round_obj, dice_result=result, dice_values=dice_values)
                                        
                                        self.stdout.write(self.style.SUCCESS(f"Settled Round {round_id} in DB: Result {result}"))
                                    
                                    # Delete processed message from stream
                                    redis_client.xdel(STREAM_NAME, message_id)
                                    
                            except Exception as event_err:
                                logger.error(f"Error processing game event {event_type} for round {round_id}: {event_err}")
                                # Don't delete if failed, so we can retry (or move to DLQ)
                                continue

                # 2. Fetch a batch of bets from Redis list
                bets_to_process = []
                for _ in range(batch_size):
                    bet_json = redis_client.lpop('bet_queue')
                    if bet_json:
                        bets_to_process.append(json.loads(bet_json))
                    else:
                        break
                
                if not bets_to_process:
                    if not events: # Only sleep if no events were processed either
                        time.sleep(0.5)
                    continue

                # 3. Process Batch in a single DB Transaction
                with transaction.atomic():
                    for bet_data in bets_to_process:
                        try:
                            user_id = bet_data['user_id']
                            round_id = bet_data['round_id']
                            number = bet_data['number']
                            chip_amount = Decimal(bet_data['chip_amount'])
                            
                            # Get Round and Wallet
                            try:
                                round_obj = GameRound.objects.get(round_id=round_id)
                            except GameRound.DoesNotExist:
                                # If round doesn't exist yet, push back to queue and wait
                                logger.warning(f"Round {round_id} not found for bet, pushing back to queue")
                                redis_client.rpush('bet_queue', json.dumps(bet_data))
                                continue

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
                            
                            # Sync Redis balance
                            redis_client.set(f"user_balance:{user_id}", str(wallet.balance), ex=3600)

                        except Exception as bet_err:
                            logger.error(f"Error processing individual bet: {bet_err}")
                            continue

                if bets_to_process:
                    self.stdout.write(self.style.SUCCESS(f"Successfully committed {len(bets_to_process)} bets to DB"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Worker Error: {e}"))
                time.sleep(2) # Wait before retry
