from collections import OrderedDict
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
    try:
        return get_game_setting(key, default)
    except Exception as e:
        logging.error(f"Error fetching setting {key}: {e}")
        return default

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GameEngine")

class GameEngine:
    def __init__(self):
        self.redis = None
        self.round_id = None
        self.status = "WAITING"
        self.last_published_status = None
        self.start_monotonic = 0
        self.end_monotonic = 0
        self.dice_result = None
        self.last_dice_values = None
        
        # Timing settings (defaults)
        self.betting_close_time = 30
        self.dice_roll_time = 38
        self.dice_result_time = 43
        self.round_end_time = 48
        
        self.last_settings_refresh = 0
        self.refresh_interval = 60 # Refresh settings every 60 seconds

    async def connect_redis(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info(f"Connected to Redis at {settings.REDIS_HOST}")

    async def acquire_lock(self):
        """Ensure only one engine runs using Redis SETNX"""
        identifier = str(uuid.uuid4())
        while True:
            try:
                if await self.redis.set(ENGINE_LOCK_KEY, identifier, ex=LOCK_TIMEOUT, nx=True):
                    logger.info(f"Acquired engine lock: {identifier}")
                    return identifier
            except Exception as e:
                logger.error(f"Redis error during lock acquisition: {e}")
            
            logger.warning("Another engine is running or Redis is down, waiting...")
            await asyncio.sleep(5)

    async def renew_lock(self, identifier):
        """Keep the lock alive"""
        while True:
            try:
                await self.redis.expire(ENGINE_LOCK_KEY, LOCK_TIMEOUT)
            except Exception as e:
                logger.error(f"Lock renewal failed: {e}")
            await asyncio.sleep(LOCK_TIMEOUT / 2)

    async def refresh_settings(self, force=False):
        """Reload game settings from database periodically (non-blocking)"""
        now = time.time()
        if not force and (now - self.last_settings_refresh) < self.refresh_interval:
            return

        try:
            # Fetch settings one by one (async)
            new_betting_close = await async_get_game_setting('BETTING_CLOSE_TIME', 30)
            new_dice_roll = await async_get_game_setting('DICE_ROLL_TIME', 38)
            new_dice_result = await async_get_game_setting('DICE_RESULT_TIME', 43)
            new_round_end = await async_get_game_setting('ROUND_END_TIME', 48)
            
            # Update local state
            self.betting_close_time = new_betting_close
            self.dice_roll_time = new_dice_roll
            self.dice_result_time = new_dice_result
            self.round_end_time = new_round_end
            
            self.last_settings_refresh = now
            logger.info(f"Settings refreshed: Betting={self.betting_close_time}s, Roll={self.dice_roll_time}s, Result={self.dice_result_time}s, End={self.round_end_time}s")
        except Exception as e:
            logger.error(f"Failed to refresh settings: {e}")

    async def start_new_round(self):
        # Trigger settings refresh (will only fetch from DB if interval has passed)
        await self.refresh_settings()
        
        self.round_id = f"R{int(time.time())}"
        self.start_monotonic = time.monotonic()
        self.end_monotonic = self.start_monotonic + self.round_end_time
        self.status = "BETTING"
        self.last_published_status = None # Reset for new round
        self.dice_result = None
        self.last_dice_values = None

        logger.info(f"New Round Started: {self.round_id}")

        event = {
            "type": "game_start",
            "round_id": self.round_id,
            "start_time": datetime.now().isoformat(),
            "durations": json.dumps({
                "betting_close_time": self.betting_close_time,
                "dice_roll_time": self.dice_roll_time,
                "dice_result_time": self.dice_result_time,
                "round_end_time": self.round_end_time
            })
        }
        try:
            await self.redis.xadd(ROUND_EVENTS_STREAM, event)
        except Exception as e:
            logger.error(f"Failed to log round start to Redis: {e}")
            
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
        # Use round_end_time as the cap for the timer
        timer = min(self.round_end_time, max(1, int(elapsed_seconds) + 1))
        
        # Determine message type based on requested logic
        msg_type = "timer"
        if legacy_type == "game_start":
            msg_type = "game_start"
        elif legacy_type == "game_end" or timer >= self.round_end_time:
            msg_type = "game_end"
        elif self.status == "ROLLING" and self.last_published_status != "ROLLING":
            msg_type = "dice_roll"
        elif self.status == "RESULT" and self.last_published_status != "RESULT":
            msg_type = "dice_result"
        
        self.last_published_status = self.status

        # Map internal status to requested external status
        external_status = self.status
        if self.status in ["WAITING_FOR_RESULT", "ROLLING"]:
            external_status = "closed"

        # Maintain exact key order using a list of tuples for json.dumps
        state_list = [
            ("type", msg_type),
            ("round_id", self.round_id),
            ("timer", timer),
            ("status", external_status),
            ("dice_result", self.dice_result)
        ]
        
        state_dict = dict(state_list)
        if self.status == "RESULT" and self.last_dice_values:
            state_dict["dice_values"] = self.last_dice_values
            for i, val in enumerate(self.last_dice_values, 1):
                state_dict[f"dice_{i}"] = val
            state_dict["dice_result"] = self.dice_result
            # Re-create ordered list for RESULT phase
            state_list = list(state_dict.items())

        try:
            payload = json.dumps(OrderedDict(state_list))
            await self.redis.set(GAME_STATE_KEY, payload, ex=5)
            await self.redis.publish(GAME_ROOM_CHANNEL, payload)
        except Exception as e:
            logger.error(f"Failed to publish state: {e}")

    async def run(self):
        await self.connect_redis()
        lock_id = await self.acquire_lock()
        asyncio.create_task(self.renew_lock(lock_id))

        # Initial settings fetch
        await self.refresh_settings(force=True)

        while True:
            await self.start_new_round()
            
            while time.monotonic() < self.end_monotonic:
                now_mono = time.monotonic()
                elapsed = now_mono - self.start_monotonic
                
                # Phase Transitions
                if elapsed >= self.round_end_time - 0.1:
                    # Final game_end message sent exactly at the end of the round
                    await self.publish_state(legacy_type="game_end")
                    break
                elif elapsed >= self.dice_result_time:
                    if self.status != "RESULT":
                        self.status = "RESULT"
                        self.last_dice_values, self.dice_result = await self.generate_dice_result()
                        # Record result in stream for workers
                        try:
                            await self.redis.xadd(ROUND_EVENTS_STREAM, {
                                "type": "dice_result",
                                "round_id": self.round_id,
                                "result": self.dice_result,
                                "dice_values": json.dumps(self.last_dice_values)
                            })
                        except Exception as e:
                            logger.error(f"Failed to log result to Redis: {e}")
                elif elapsed >= self.dice_roll_time:
                    self.status = "ROLLING"
                elif elapsed >= self.betting_close_time:
                    self.status = "WAITING_FOR_RESULT"
                
                await self.publish_state()
                await asyncio.sleep(1)
            
            # Small gap between rounds
            await asyncio.sleep(0.5)

if __name__ == "__main__":
    engine = GameEngine()
    asyncio.run(engine.run())
