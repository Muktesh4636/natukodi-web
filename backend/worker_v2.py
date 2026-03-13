import os
import django
import json
import logging
import asyncio
import redis.asyncio as redis
from decimal import Decimal
from datetime import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
django.setup()

from django.conf import settings
from game.models import GameRound, Bet
from accounts.models import User, Wallet, Transaction
from django.db import transaction
from asgiref.sync import sync_to_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WorkerV2")

try:
    from smart_dice_engine import update_player_state_sync
    _SMART_ENGINE_AVAILABLE = True
except ImportError:
    _SMART_ENGINE_AVAILABLE = False
    logger.warning("smart_dice_engine not available — player state updates disabled")

REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

BET_STREAM = "bet_stream"
SETTLE_STREAM = "settle_stream"
GROUP_NAME = "worker_group"
CONSUMER_NAME = f"worker_{os.uname().nodename}"

class WorkerV2:
    def __init__(self):
        self.redis = None

    async def connect_redis(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info(f"Connected to Redis. Consumer: {CONSUMER_NAME}")

    async def setup_groups(self):
        for stream in [BET_STREAM, SETTLE_STREAM]:
            try:
                await self.redis.xgroup_create(stream, GROUP_NAME, id="0", mkstream=True)
            except Exception:
                pass # Already exists

    async def process_bets(self):
        """Batch process bets from Redis Stream"""
        while True:
            try:
                # Read batch
                messages = await self.redis.xreadgroup(GROUP_NAME, CONSUMER_NAME, {BET_STREAM: ">"}, count=50, block=2000)
                if not messages:
                    # Periodic XAUTOCLAIM to recover stuck messages
                    await self.redis.xautoclaim(BET_STREAM, GROUP_NAME, CONSUMER_NAME, 10000, "0-0", count=50)
                    continue

                for stream, msg_list in messages:
                    bet_batch = []
                    msg_ids = []
                    for msg_id, data in msg_list:
                        bet_batch.append(data)
                        msg_ids.append(msg_id)

                    if bet_batch:
                        # Atomic DB Transaction
                        success_count = await self.db_save_bets(bet_batch)
                        # Acknowledge messages
                        if success_count > 0:
                            await self.redis.xack(BET_STREAM, GROUP_NAME, *msg_ids)
                            logger.info(f"Processed batch of {success_count} bets")

            except Exception as e:
                logger.error(f"Error in process_bets: {e}")
                await asyncio.sleep(2)

    @sync_to_async
    def db_save_bets(self, bet_batch):
        count = 0
        try:
            with transaction.atomic():
                for data in bet_batch:
                    try:
                        user_id = data['user_id']
                        round_id = data['round_id']
                        number = data['number']
                        amount = Decimal(data['chip_amount'])
                        
                        # PK-based Idempotency: In a real system, you'd generate a UUID for the bet_id
                        # and use it as the PRIMARY KEY. Here we'll use a unique constraint check.
                        
                        user = User.objects.get(id=user_id)
                        round_obj = GameRound.objects.get(round_id=round_id)
                        
                        # Create Bet
                        Bet.objects.create(
                            user=user,
                            round=round_obj,
                            number=number,
                            chip_amount=amount
                        )
                        
                        # Update Wallet (deduct releases unavaliable_balance when betting)
                        wallet = Wallet.objects.select_for_update().get(user=user)
                        balance_before = wallet.balance
                        if not wallet.deduct(amount):
                            raise ValueError(f"Insufficient balance for user {user_id}")
                        
                        # Transaction log
                        Transaction.objects.create(
                            user=user,
                            transaction_type='BET',
                            amount=amount,
                            balance_before=balance_before,
                            balance_after=wallet.balance,
                            description=f"Bet on {number} in round {round_id}"
                        )
                        # Update smart dice player state
                        if _SMART_ENGINE_AVAILABLE:
                            try:
                                sync_redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
                                update_player_state_sync(
                                    sync_redis,
                                    user_id=int(user_id),
                                    won=False,  # bets are losses until settlement
                                    win_amount=0,
                                    current_balance=wallet.balance,
                                )
                            except Exception as se:
                                logger.debug(f"Player state update skipped: {se}")

                        count += 1
                    except Exception as e:
                        logger.error(f"Failed to process bet in batch: {e}")
            return count
        except Exception as e:
            logger.error(f"Batch transaction failed: {e}")
            return 0

    async def run(self):
        await self.connect_redis()
        await self.setup_groups()
        # Start processing loops
        await asyncio.gather(
            self.process_bets(),
            # self.process_settlements() # To be implemented similarly
        )

if __name__ == "__main__":
    worker = WorkerV2()
    asyncio.run(worker.run())
