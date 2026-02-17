import json
import logging
import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone
import redis
from django.conf import settings
from game.models import GameRound, Bet, DiceResult
from accounts.models import Wallet, Transaction, User

logger = logging.getLogger('game.bet_worker')

class Command(BaseCommand):
    help = 'Process bets from Redis Stream (bet_stream) using consumer group and write to Database in batches'

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
        BET_STREAM = "bet_stream"
        BET_GROUP = "worker_group"
        CONSUMER_NAME = f"worker_{time.time()}"  # Unique consumer name
        
        # Create bet_stream consumer group if it doesn't exist
        try:
            redis_client.xgroup_create(BET_STREAM, BET_GROUP, id='0', mkstream=True)
            self.stdout.write(self.style.SUCCESS(f'✅ Created consumer group {BET_GROUP} on {BET_STREAM}'))
        except redis.exceptions.ResponseError as e:
            if 'BUSYGROUP' in str(e):
                self.stdout.write(self.style.SUCCESS(f'✅ Consumer group {BET_GROUP} already exists'))
            else:
                self.stdout.write(self.style.WARNING(f'Note: {e}'))
        
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
                                from django.db import connections
                                connections.close_all()
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

                # 2. Fetch a batch of bets from Redis Stream using consumer group
                bets_to_process = []
                message_ids = []
                
                try:
                    # Read messages from bet_stream using consumer group
                    messages = redis_client.xreadgroup(
                        BET_GROUP, 
                        CONSUMER_NAME, 
                        {BET_STREAM: '>'}, 
                        count=batch_size, 
                        block=1000  # Block for 1 second
                    )
                    
                    if messages:
                        for stream, msg_list in messages:
                            for msg_id, data in msg_list:
                                bets_to_process.append(data)
                                message_ids.append(msg_id)
                    
                    # Recover pending messages (stuck messages from crashed workers)
                    if not bets_to_process:
                        try:
                            # Use xpending to check for pending messages first
                            pending_info = redis_client.xpending(BET_STREAM, BET_GROUP)
                            if pending_info and pending_info['pending'] > 0:
                                # Simple recovery: just read from the beginning again
                                # This is less efficient but compatible with older Redis versions
                                recovery_messages = redis_client.xreadgroup(
                                    BET_GROUP,
                                    f"{CONSUMER_NAME}_recovery",
                                    {BET_STREAM: '0'},
                                    count=min(10, batch_size),  # Recover fewer messages
                                    block=1
                                )
                                if recovery_messages:
                                    for stream, msg_list in recovery_messages:
                                        for msg_id, data in msg_list:
                                            bets_to_process.append(data)
                                            message_ids.append(msg_id)
                                            logger.info(f"Recovered pending message {msg_id}")
                        except Exception as recovery_err:
                            logger.warning(f"Pending message recovery failed: {recovery_err}")
                            # Continue without recovery - not critical
                
                except redis.exceptions.ResponseError as e:
                    if 'NOGROUP' in str(e):
                        # Group doesn't exist, try to create it
                        try:
                            redis_client.xgroup_create(BET_STREAM, BET_GROUP, id='0', mkstream=True)
                            self.stdout.write(self.style.SUCCESS(f'✅ Created consumer group {BET_GROUP}'))
                        except:
                            pass
                    else:
                        logger.error(f"Error reading from bet_stream: {e}")
                
                if not bets_to_process:
                    if not events: # Only sleep if no events were processed either
                        time.sleep(0.5)
                    continue

                # 3. Process Batch in a single DB Transaction
                processed_count = 0
                ack_ids = []
                
                from django.db import connections
                connections.close_all()
                with transaction.atomic():
                    for idx, bet_data in enumerate(bets_to_process):
                        try:
                            user_id = int(bet_data['user_id'])
                            round_id = bet_data['round_id']
                            number = int(bet_data['number'])
                            chip_amount = Decimal(bet_data['chip_amount'])
                            
                            # Get Round
                            try:
                                round_obj = GameRound.objects.get(round_id=round_id)
                            except GameRound.DoesNotExist:
                                # If round doesn't exist yet, don't ACK - let it retry later
                                logger.warning(f"Round {round_id} not found for bet, will retry")
                                continue

                            # IMPORTANT: Balance was already deducted in Redis (Lua script in place_bet API)
                            # We do NOT deduct again here - Redis is the real-time ledger
                            # DB wallet table will be synced by reconciliation job periodically
                            
                            # Get current Redis balance for transaction log (balance already deducted in Redis)
                            balance_key = f"user_balance:{user_id}"
                            redis_balance = redis_client.get(balance_key)
                            if redis_balance:
                                balance_after = Decimal(redis_balance)
                                balance_before = balance_after + chip_amount  # Calculate before from after
                            else:
                                # Fallback: get from DB (shouldn't happen if Redis is working)
                                wallet = Wallet.objects.get(user_id=user_id)
                                balance_after = wallet.balance
                                balance_before = balance_after + chip_amount
                                logger.warning(f"Redis balance not found for user {user_id}, using DB balance")
                            
                            # Create Bet record (balance already deducted in Redis)
                            Bet.objects.create(
                                user_id=user_id,
                                round=round_obj,
                                number=number,
                                chip_amount=chip_amount
                            )
                            
                            # Create Transaction log (for audit trail)
                            Transaction.objects.create(
                                user_id=user_id,
                                transaction_type='BET',
                                amount=chip_amount,
                                balance_before=balance_before,
                                balance_after=balance_after,
                                description=f"Bet on {number} in round {round_id} (Balance deducted in Redis)"
                            )
                            
                            # Note: We do NOT update DB wallet balance here
                            # Redis is the source of truth for real-time balance
                            # Reconciliation job will sync Redis → DB periodically
                            
                            # Mark for acknowledgment
                            ack_ids.append(message_ids[idx])
                            processed_count += 1

                        except Exception as bet_err:
                            logger.error(f"Error processing individual bet: {bet_err}")
                            # Don't ACK failed messages so they can be retried
                            continue
                
                # Acknowledge successfully processed messages
                if ack_ids:
                    try:
                        redis_client.xack(BET_STREAM, BET_GROUP, *ack_ids)
                        self.stdout.write(self.style.SUCCESS(f"Successfully committed {processed_count} bets to DB and acknowledged"))
                    except Exception as ack_err:
                        logger.error(f"Error acknowledging messages: {ack_err}")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Worker Error: {e}"))
                time.sleep(2) # Wait before retry
