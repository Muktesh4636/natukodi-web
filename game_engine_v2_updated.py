import asyncio
import json
import logging
import time
import uuid
import os
import django
import random
from datetime import datetime
import redis.asyncio as redis

# Setup Django for settings access
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
django.setup()

from django.conf import settings
from asgiref.sync import sync_to_async
from game.utils import get_game_setting, determine_winning_number
from game.models import GameRound, DiceResult

# Async wrapper for get_game_setting (database access)
@sync_to_async
def async_get_game_setting(key, default):
    """Async wrapper for get_game_setting"""
    return get_game_setting(key, default)

@sync_to_async
def get_preset_dice_result(round_id):
    """Check if admin has preset a dice result for this round"""
    try:
        # Check DiceResult model first
        preset = DiceResult.objects.filter(round__round_id=round_id).first()
        if preset:
            return preset.result

        # Also check GameRound itself
        round_obj = GameRound.objects.filter(round_id=round_id).first()
        if round_obj and round_obj.dice_result:
            return round_obj.dice_result
    except Exception as e:
        logging.error(f"Error checking preset dice: {e}")
    return None

# Configuration
REDIS_URL = f'redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0'
if settings.REDIS_PASSWORD and settings.REDIS_PASSWORD != 'None' and settings.REDIS_PASSWORD != '':
    REDIS_URL = f'redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0'

GAME_ROOM_CHANNEL = "game_room"
ROUND_EVENTS_STREAM = "round_events_stream"
GAME_STATE_KEY = "current_game_state"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 10  # seconds

# Default Game time points (seconds from round start)
BETTING_CLOSE_TIME = 30
DICE_ROLL_TIME = 35
DICE_RESULT_TIME = 45
ROUND_END_TIME = 70

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GameEngine")

class GameEngine:
    def __init__(self):
        self.redis = None
        self.round_id = None
        self.status = "WAITING"
        self.start_monotonic = 0
        self.end_monotonic = 0
        self.dice_result = None
        self.last_dice_values = None
        
        # Timing settings
        self.betting_close_time = BETTING_CLOSE_TIME
        self.dice_roll_time = DICE_ROLL_TIME
        self.dice_result_time = DICE_RESULT_TIME
        self.round_end_time = ROUND_END_TIME

    async def connect_redis(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info(f"Connected to Redis at {settings.REDIS_HOST}")

    async def acquire_lock(self):
        """Ensure only one engine runs using Redis SETNX"""
        identifier = str(uuid.uuid4())
        while True:
            if await self.redis.set(ENGINE_LOCK_KEY, identifier, ex=LOCK_TIMEOUT, nx=True):
                logger.info(f"Acquired engine lock: {identifier}")
                return identifier
            logger.warning("Another engine is running, waiting...")
            await asyncio.sleep(5)

    async def renew_lock(self, identifier):
        """Keep the lock alive"""
        while True:
            try:
                await self.redis.expire(ENGINE_LOCK_KEY, LOCK_TIMEOUT)
            except Exception as e:
                logger.error(f"Lock renewal failed: {e}")
            await asyncio.sleep(LOCK_TIMEOUT / 2)

    async def refresh_settings(self):
        """Reload game settings from database each round"""
        self.betting_close_time = await async_get_game_setting('BETTING_CLOSE_TIME', 30)
        self.dice_roll_time = await async_get_game_setting('DICE_ROLL_TIME', 35)
        self.dice_result_time = await async_get_game_setting('DICE_RESULT_TIME', 45)
        self.round_end_time = await async_get_game_setting('ROUND_END_TIME', 70)
        logger.info(f"Settings refreshed: Betting={self.betting_close_time}s, Roll={self.dice_roll_time}s, Result={self.dice_result_time}s, End={self.round_end_time}s")

    async def start_new_round(self):
        await self.refresh_settings()
        
        self.round_id = f"R{int(time.time())}"
        self.start_monotonic = time.monotonic()
        self.end_monotonic = self.start_monotonic + self.round_end_time
        self.status = "BETTING"
        self.dice_result = None
        self.last_dice_values = None

        logger.info(f"New Round Started: {self.round_id}")

        event = {
            "type": "game_start",
            "round_id": self.round_id,
            "start_time": datetime.utcnow().isoformat(),
            "durations": json.dumps({
                "betting_close_time": self.betting_close_time,
                "dice_roll_time": self.dice_roll_time,
                "dice_result_time": self.dice_result_time,
                "round_end_time": self.round_end_time
            })
        }
        await self.redis.xadd(ROUND_EVENTS_STREAM, event)
        await self.publish_state(legacy_type="game_start")

    async def generate_dice_result(self):
        # Check for admin preset result
        preset = await get_preset_dice_result(self.round_id)
        if preset:
            logger.info(f"Using admin preset result for round {self.round_id}: {preset}")
            if ',' in str(preset):
                dice = []
                for x in str(preset).split(','):
                    try:
                        dice.append(int(x.strip()))
                    except ValueError:
                        pass
                while len(dice) < 6: dice.append(random.randint(1, 6))
                dice = dice[:6]
            else:
                try:
                    dice = [int(preset)] * 6
                except ValueError:
                    dice = [random.randint(1, 6) for _ in range(6)]
            
            result_str = determine_winning_number(dice)
            return dice, result_str

        # Random generation
        dice = [random.randint(1, 6) for _ in range(6)]
        result_str = determine_winning_number(dice)
        return dice, result_str

    async def publish_state(self, legacy_type=None):
        """Broadcast game state to all connected clients via Redis Pub/Sub"""
        now_mono = time.monotonic()
        elapsed_seconds = now_mono - self.start_monotonic
        timer = max(1, int(elapsed_seconds) + 1)
        
        state = {
            "type": legacy_type or "game_state",
            "round_id": self.round_id,
            "timer": timer,
            "status": self.status,
            "is_rolling": self.status == "ROLLING",
            "end_time": int(time.time() + (self.betting_close_time - (time.monotonic() - self.start_monotonic))) if self.status == "BETTING" else int(time.time()),
            "dice_result": self.dice_result,
            "end_time": int(time.time() + (self.betting_close_time - (time.monotonic() - self.start_monotonic))) if self.status == "BETTING" else int(time.time()),
            "dice_result": self.dice_result,
            "server_time": int(time.time())
        }
        
        if self.status == "RESULT" and self.last_dice_values:
            state["dice_values"] = self.last_dice_values
            for i, val in enumerate(self.last_dice_values, 1):
                state[f"dice_{i}"] = val
            state["dice_result"] = self.dice_result

        payload = json.dumps(state)
        await self.redis.set(GAME_STATE_KEY, payload, ex=5)
        await self.redis.publish(GAME_ROOM_CHANNEL, payload)

    async def run(self):
        await self.connect_redis()
        lock_id = await self.acquire_lock()
        asyncio.create_task(self.renew_lock(lock_id))

        while True:
            await self.start_new_round()
            
            while time.monotonic() < self.end_monotonic:
                now_mono = time.monotonic()
                elapsed = now_mono - self.start_monotonic
                
                # Phase Transitions
                if elapsed >= self.round_end_time:
                    break
                elif elapsed >= self.dice_result_time:
                    if self.status != "RESULT":
                        self.status = "RESULT"
                        self.last_dice_values, self.dice_result = await self.generate_dice_result()
                        # Record result in stream for workers
                        await self.redis.xadd(ROUND_EVENTS_STREAM, {
                            "type": "dice_result",
                            "round_id": self.round_id,
                            "result": self.dice_result,
                            "dice_values": json.dumps(self.last_dice_values)
                        })
                elif elapsed >= self.dice_roll_time:
                    self.status = "ROLLING"
                elif elapsed >= self.betting_close_time:
                    self.status = "WAITING_FOR_RESULT"
                
                await self.publish_state()
                await asyncio.sleep(1)
            
            # Round over
            await asyncio.sleep(1)

if __name__ == "__main__":
    engine = GameEngine()
    asyncio.run(engine.run())
