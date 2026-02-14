import os
import django
import json
import logging
import asyncio
import redis.asyncio as redis
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
django.setup()

from django.conf import settings
from game.models import GameRound, DiceResult, Bet
from accounts.models import User, Wallet, Transaction
from game.views import calculate_payouts
from django.utils import timezone
from asgiref.sync import sync_to_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RoundWorker")

REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

STREAM_NAME = "round_events_stream"
GROUP_NAME = "db_persistence_group"
CONSUMER_NAME = "worker_1"

async def process_events():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Create consumer group if not exists
    try:
        await r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except Exception:
        pass # Already exists

    logger.info("Worker started, waiting for events and bets...")

    while True:
        try:
            # 1. Process Round Events (from Stream)
            messages = await r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=1, block=1000)
            if messages:
                for stream, msg_list in messages:
                    for msg_id, data in msg_list:
                        event_type = data.get("type")
                        round_id = data.get("round_id")
                        
                        if event_type == "round_start":
                            durations = json.loads(data.get("durations", "{}"))
                            await sync_to_async(GameRound.objects.get_or_create)(
                                round_id=round_id,
                                defaults={
                                    'status': 'BETTING',
                                    'betting_close_seconds': durations.get("betting", 30),
                                    'dice_roll_seconds': durations.get("roll", 5),
                                    'dice_result_seconds': durations.get("result", 10),
                                    'round_end_seconds': sum(durations.values())
                                }
                            )
                            logger.info(f"Saved Round Start: {round_id}")

                        elif event_type == "round_result":
                            dice_values = json.loads(data.get("dice_values", "[]"))
                            result_str = data.get("result")
                            
                            def update_db():
                                try:
                                    round_obj = GameRound.objects.get(round_id=round_id)
                                    for i, val in enumerate(dice_values, 1):
                                        setattr(round_obj, f'dice_{i}', val)
                                    round_obj.dice_result = result_str
                                    round_obj.status = 'RESULT'
                                    round_obj.result_time = timezone.now()
                                    round_obj.save()
                                    DiceResult.objects.update_or_create(round=round_obj, defaults={'result': result_str})
                                    calculate_payouts(round_obj, dice_result=result_str, dice_values=dice_values)
                                    round_obj.status = 'COMPLETED'
                                    round_obj.end_time = timezone.now()
                                    round_obj.save()
                                    return True
                                except GameRound.DoesNotExist:
                                    return False

                            await sync_to_async(update_db)()
                            logger.info(f"Processed Results & Payouts: {round_id}")

                        await r.xack(STREAM_NAME, GROUP_NAME, msg_id)

            # 2. Process Bets (from List) - Bulk Insert
            bets_data = []
            for _ in range(50): # Batch size 50
                raw_bet = await r.lpop("bet_queue")
                if not raw_bet:
                    break
                bets_data.append(json.loads(raw_bet))

            if bets_data:
                def bulk_save_bets(data_list):
                    from django.db import transaction
                    with transaction.atomic():
                        bets_to_create = []
                        for data in data_list:
                            try:
                                user = User.objects.get(id=data['user_id'])
                                round_obj = GameRound.objects.get(round_id=data['round_id'])
                                bets_to_create.append(Bet(
                                    user=user, round=round_obj, number=data['number'],
                                    chip_amount=Decimal(data['chip_amount'])
                                ))
                                # Update wallet and create transaction
                                wallet = user.wallet
                                balance_before = wallet.balance
                                wallet.balance -= Decimal(data['chip_amount'])
                                wallet.save()
                                Transaction.objects.create(
                                    user=user, transaction_type='BET', amount=Decimal(data['chip_amount']),
                                    balance_before=balance_before, balance_after=wallet.balance,
                                    description=f"Bet on {data['number']} in round {data['round_id']}"
                                )
                            except Exception as e:
                                logger.error(f"Failed to process bet in batch: {e}")
                        if bets_to_create:
                            Bet.objects.bulk_create(bets_to_create)
                    return len(bets_to_create)

                count = await sync_to_async(bulk_save_bets)(bets_data)
                logger.info(f"Bulk saved {count} bets to database")

        except Exception as e:
            logger.exception(f"Error in worker loop: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(process_events())
