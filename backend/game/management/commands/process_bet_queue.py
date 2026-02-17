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
            return

        STREAM_NAME = "round_events_stream"
        EVENT_GROUP = "event_worker_group"
        BET_STREAM = "bet_stream"
        BET_GROUP = "worker_group"
        CONSUMER_NAME = f"worker_{time.time()}"
        
        # Create groups
        for stream, group in [(STREAM_NAME, EVENT_GROUP), (BET_STREAM, BET_GROUP)]:
            try:
                redis_client.xgroup_create(stream, group, id='0', mkstream=True)
                self.stdout.write(self.style.SUCCESS(f'✅ Created consumer group {group} on {stream}'))
            except redis.exceptions.ResponseError as e:
                if 'BUSYGROUP' not in str(e):
                    self.stdout.write(self.style.WARNING(f'Note: {e}'))

        while True:
            try:
                # 1. ALWAYS process Game Events first
                events = redis_client.xreadgroup(EVENT_GROUP, CONSUMER_NAME, {STREAM_NAME: '>'}, count=5, block=10)
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
                                        self.stdout.write(self.style.SUCCESS(f"Created Round {round_id}"))
                                    elif event_type == 'round_result':
                                        result = data.get('result')
                                        dice_values = json.loads(data.get('dice_values', '[]'))
                                        round_obj = GameRound.objects.get(round_id=round_id)
                                        round_obj.status = 'RESULT'
                                        round_obj.dice_result = result
                                        round_obj.result_time = data.get('end_time')
                                        if len(dice_values) == 6:
                                            for i, val in enumerate(dice_values, 1):
                                                setattr(round_obj, f'dice_{i}', val)
                                        round_obj.save()
                                        DiceResult.objects.update_or_create(round=round_obj, defaults={'result': result})
                                        from game.views import calculate_payouts
                                        calculate_payouts(round_obj, dice_result=result, dice_values=dice_values)
                                        self.stdout.write(self.style.SUCCESS(f"Settled Round {round_id}"))
                                    redis_client.xack(STREAM_NAME, EVENT_GROUP, message_id)
                            except Exception as e:
                                logger.error(f"Event error {event_type} {round_id}: {e}")

                # 2. Process Bets
                messages = redis_client.xreadgroup(BET_GROUP, CONSUMER_NAME, {BET_STREAM: '>'}, count=20, block=10)
                if not messages:
                    # Check for pending (stuck) bets
                    pending = redis_client.xpending(BET_STREAM, BET_GROUP)
                    if pending and pending['pending'] > 0:
                        messages = redis_client.xreadgroup(BET_GROUP, f"{CONSUMER_NAME}_rec", {BET_STREAM: '0'}, count=10, block=1)

                if messages:
                    for stream, msg_list in messages:
                        bets_to_process = []
                        message_ids = []
                        for msg_id, data in msg_list:
                            bets_to_process.append(data)
                            message_ids.append(msg_id)
                        
                        ack_ids = []
                        from django.db import connections
                        connections.close_all()
                        with transaction.atomic():
                            for idx, bet_data in enumerate(bets_to_process):
                                try:
                                    round_id = bet_data['round_id']
                                    try:
                                        round_obj = GameRound.objects.get(round_id=round_id)
                                    except GameRound.DoesNotExist:
                                        logger.warning(f"Round {round_id} not found, skipping for now")
                                        continue
                                    
                                    user_id = int(bet_data['user_id'])
                                    number = int(bet_data['number'])
                                    chip_amount = Decimal(bet_data['chip_amount'])
                                    
                                    # Create records
                                    Bet.objects.create(user_id=user_id, round=round_obj, number=number, chip_amount=chip_amount)
                                    
                                    # Transaction log
                                    bal_after = Decimal(redis_client.get(f"user_balance:{user_id}") or 0)
                                    Transaction.objects.create(
                                        user_id=user_id, transaction_type='BET', amount=chip_amount,
                                        balance_before=bal_after + chip_amount, balance_after=bal_after,
                                        description=f"Bet on {number} in round {round_id}"
                                    )
                                    ack_ids.append(message_ids[idx])
                                except Exception as e:
                                    logger.error(f"Bet error: {e}")
                        
                        if ack_ids:
                            redis_client.xack(BET_STREAM, BET_GROUP, *ack_ids)
                            self.stdout.write(self.style.SUCCESS(f"Processed {len(ack_ids)} bets"))

                if not events and not messages:
                    time.sleep(0.1)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Worker Error: {e}"))
                time.sleep(1)
