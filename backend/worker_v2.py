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

    async def _process_stream_messages(self, stream_name, msg_list, handler_fn, stream_label):
        """Process a list of (msg_id, data) tuples via handler_fn and ack them."""
        if not msg_list:
            return
        batch = []
        msg_ids = []
        for msg_id, data in msg_list:
            batch.append(data)
            msg_ids.append(msg_id)
        if batch:
            count = await handler_fn(batch)
            # Always ack (even partial failures) to avoid infinite retry loops.
            await self.redis.xack(stream_name, GROUP_NAME, *msg_ids)
            logger.info(f"[{stream_label}] Acked {len(msg_ids)} messages, processed {count}")

    async def process_bets(self):
        """Batch process bets from Redis Stream"""
        # On startup, drain any pending messages that belong to this consumer
        try:
            pending = await self.redis.xreadgroup(GROUP_NAME, CONSUMER_NAME, {BET_STREAM: "0"}, count=200)
            if pending:
                for _, msg_list in pending:
                    await self._process_stream_messages(BET_STREAM, msg_list, self.db_save_bets, "BET-pending")
        except Exception as e:
            logger.error(f"Error draining pending bets: {e}")

        while True:
            try:
                # Reclaim messages stuck with other consumers for >30s
                try:
                    next_id, reclaimed, _ = await self.redis.xautoclaim(
                        BET_STREAM, GROUP_NAME, CONSUMER_NAME, 30000, "0-0", count=50
                    )
                    if reclaimed:
                        await self._process_stream_messages(BET_STREAM, reclaimed, self.db_save_bets, "BET-reclaim")
                except Exception:
                    pass

                # Read new messages
                messages = await self.redis.xreadgroup(GROUP_NAME, CONSUMER_NAME, {BET_STREAM: ">"}, count=50, block=2000)
                if not messages:
                    continue
                for _, msg_list in messages:
                    await self._process_stream_messages(BET_STREAM, msg_list, self.db_save_bets, "BET")

            except Exception as e:
                logger.error(f"Error in process_bets: {e}")
                await asyncio.sleep(2)

    @sync_to_async
    def db_save_bets(self, bet_batch):
        count = 0
        for data in bet_batch:
            try:
                user_id = data['user_id']
                round_id = data['round_id']
                number = int(data['number'])
                amount = Decimal(data['chip_amount'])

                user = User.objects.get(id=user_id)
                round_obj, _ = GameRound.objects.get_or_create(round_id=round_id, defaults={'status': 'BETTING'})

                # Idempotency: skip if bet already recorded
                if Bet.objects.filter(user=user, round=round_obj, number=number, chip_amount=amount).exists():
                    count += 1
                    continue

                with transaction.atomic():
                    # Record the bet
                    Bet.objects.create(user=user, round=round_obj, number=number, chip_amount=amount)

                    # Sync DB wallet (Redis already deducted; apply same deduction to DB)
                    wallet = Wallet.objects.select_for_update().get(user=user)
                    balance_before = wallet.balance
                    if wallet.balance >= amount:
                        wallet.deduct(amount)
                        balance_after = wallet.balance
                    else:
                        # Redis was already deducted; trust Redis and floor DB to 0 instead of going negative
                        balance_after = wallet.balance
                        logger.warning(f"DB wallet low for user {user_id} (balance={wallet.balance}, bet={amount}); skipping DB deduction")

                    Transaction.objects.create(
                        user=user,
                        transaction_type='BET',
                        amount=amount,
                        balance_before=balance_before,
                        balance_after=balance_after,
                        description=f"Bet on {number} in round {round_id}",
                    )
                count += 1
            except Exception as e:
                logger.error(f"Failed to save bet (user={data.get('user_id')}, round={data.get('round_id')}): {e}")
        return count

    async def process_settlements(self):
        """Process round settlement events from Redis Stream and pay out winners."""
        # Drain pending settle messages on startup
        try:
            pending = await self.redis.xreadgroup(GROUP_NAME, CONSUMER_NAME, {SETTLE_STREAM: "0"}, count=200)
            if pending:
                for _, msg_list in pending:
                    await self._process_stream_messages(SETTLE_STREAM, msg_list, self.db_settle_round, "SETTLE-pending")
        except Exception as e:
            logger.error(f"Error draining pending settlements: {e}")

        while True:
            try:
                # Reclaim stuck settle messages
                try:
                    next_id, reclaimed, _ = await self.redis.xautoclaim(
                        SETTLE_STREAM, GROUP_NAME, CONSUMER_NAME, 30000, "0-0", count=50
                    )
                    if reclaimed:
                        await self._process_stream_messages(SETTLE_STREAM, reclaimed, self.db_settle_round, "SETTLE-reclaim")
                except Exception:
                    pass

                messages = await self.redis.xreadgroup(GROUP_NAME, CONSUMER_NAME, {SETTLE_STREAM: ">"}, count=20, block=2000)
                if not messages:
                    continue
                for _, msg_list in messages:
                    await self._process_stream_messages(SETTLE_STREAM, msg_list, self.db_settle_round, "SETTLE")

            except Exception as e:
                logger.error(f"Error in process_settlements: {e}")
                await asyncio.sleep(2)

    @sync_to_async
    def db_settle_round(self, settle_batch):
        from collections import Counter
        from django.db.models import F

        count = 0
        for data in settle_batch:
            try:
                round_id = data['round_id']
                dice_values_raw = data.get('dice_values', '[]')
                dice_values = json.loads(dice_values_raw) if isinstance(dice_values_raw, str) else dice_values_raw

                round_obj, _ = GameRound.objects.get_or_create(round_id=round_id, defaults={'status': 'BETTING'})

                # Idempotency: skip if already settled
                if round_obj.status == 'COMPLETED':
                    count += 1
                    continue

                with transaction.atomic():
                    # Save dice values to round
                    if len(dice_values) >= 6:
                        round_obj.dice_1 = dice_values[0]
                        round_obj.dice_2 = dice_values[1]
                        round_obj.dice_3 = dice_values[2]
                        round_obj.dice_4 = dice_values[3]
                        round_obj.dice_5 = dice_values[4]
                        round_obj.dice_6 = dice_values[5]

                    # Determine winning numbers (appeared 2+ times)
                    counts = Counter(dice_values)
                    winning_numbers = [n for n, c in counts.items() if c >= 2]
                    round_obj.dice_result = ','.join(str(n) for n in winning_numbers)
                    round_obj.status = 'COMPLETED'
                    round_obj.save()

                    # Pay out winners
                    for winning_number in winning_numbers:
                        frequency = counts[winning_number]
                        payout_multiplier = Decimal(str(frequency))

                        winning_bets = Bet.objects.filter(round=round_obj, number=winning_number, is_winner=False)
                        for bet in winning_bets:
                            total_payout = bet.chip_amount * (1 + payout_multiplier)
                            bet.payout_amount = total_payout
                            bet.is_winner = True
                            bet.save()

                            wallet = Wallet.objects.select_for_update().get(user=bet.user)
                            balance_before = wallet.balance
                            Wallet.objects.filter(user_id=bet.user.id).update(balance=F('balance') + total_payout)
                            wallet.refresh_from_db()
                            balance_after = wallet.balance

                            Transaction.objects.create(
                                user=bet.user,
                                transaction_type='WIN',
                                amount=total_payout,
                                balance_before=balance_before,
                                balance_after=balance_after,
                                description=f"Win on {winning_number} (x{frequency}) in round {round_id}",
                            )

                            # Sync Redis balance for winner
                            try:
                                import redis as sync_redis_lib
                                sync_r = sync_redis_lib.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True)
                                sync_r.set(f"user_balance:{bet.user.id}", str(balance_after), ex=3600)
                            except Exception as re:
                                logger.warning(f"Redis balance sync failed for user {bet.user.id}: {re}")

                    # Mark losers
                    Bet.objects.filter(round=round_obj, is_winner=False).update(payout_amount=Decimal('0.00'))

                logger.info(f"Settled round {round_id}: dice={dice_values}, winners={winning_numbers}")
                count += 1
            except Exception as e:
                logger.error(f"Failed to settle round {data.get('round_id')}: {e}")
        return count

    async def run(self):
        await self.connect_redis()
        await self.setup_groups()
        # Start processing loops
        await asyncio.gather(
            self.process_bets(),
            self.process_settlements(),
        )

if __name__ == "__main__":
    worker = WorkerV2()
    asyncio.run(worker.run())
