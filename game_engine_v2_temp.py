import asyncio
import json
import logging
import time
import uuid
import os
import django
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

# Game time points (seconds from round start) - loaded from database settings
BETTING_CLOSE_TIME = 30  # When betting closes
DICE_ROLL_TIME = 35  # When dice roll happens
DICE_RESULT_TIME = 45  # When result is shown
ROUND_END_TIME = 70  # When round ends

# Calculate durations for backward compatibility
BETTING_DURATION = BETTING_CLOSE_TIME
DICE_ROLL_DURATION = DICE_ROLL_TIME - BETTING_CLOSE_TIME
RESULT_DISPLAY_DURATION = DICE_RESULT_TIME - DICE_ROLL_TIME
TOTAL_ROUND_DURATION = ROUND_END_TIME

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

    async def start_new_round(self):
        # Reload game settings each round
        global BETTING_CLOSE_TIME, DICE_ROLL_TIME, DICE_RESULT_TIME, ROUND_END_TIME
        global BETTING_DURATION, DICE_ROLL_DURATION, RESULT_DISPLAY_DURATION, TOTAL_ROUND_DURATION
        
        BETTING_CLOSE_TIME = await async_get_game_setting('BETTING_CLOSE_TIME', 30)
        DICE_ROLL_TIME = await async_get_game_setting('DICE_ROLL_TIME', 35)
        DICE_RESULT_TIME = await async_get_game_setting('DICE_RESULT_TIME', 45)
        ROUND_END_TIME = await async_get_game_setting('ROUND_END_TIME', 70)
        
        BETTING_DURATION = BETTING_CLOSE_TIME
        DICE_ROLL_DURATION = DICE_ROLL_TIME - BETTING_CLOSE_TIME
        RESULT_DISPLAY_DURATION = DICE_RESULT_TIME - DICE_ROLL_TIME
        TOTAL_ROUND_DURATION = ROUND_END_TIME
        
        self.round_id = f"R{int(time.time())}"
        self.start_monotonic = time.monotonic()
        self.end_monotonic = self.start_monotonic + TOTAL_ROUND_DURATION
        self.status = "BETTING"
        self.dice_result = None
        
        logger.info(f"New Round Started: {self.round_id} | Betting: 1-{BETTING_CLOSE_TIME}s | Roll: {BETTING_CLOSE_TIME+1}-{DICE_ROLL_TIME}s | Result: {DICE_ROLL_TIME+1}-{DICE_RESULT_TIME}s | End: {ROUND_END_TIME}s")
        
        event = {
            "type": "round_start",
            "round_id": self.round_id,
            "start_time": datetime.utcnow().isoformat(),
            "durations": json.dumps({
                "betting_close_time": BETTING_CLOSE_TIME,
                "dice_roll_time": DICE_ROLL_TIME,
                "dice_result_time": DICE_RESULT_TIME,
                "round_end_time": ROUND_END_TIME,
                "betting": BETTING_DURATION,
                "roll": DICE_ROLL_DURATION,
                "result": RESULT_DISPLAY_DURATION
            })
        }
        await self.redis.xadd(ROUND_EVENTS_STREAM, event)

    async def generate_dice_result(self):
        import random
        from collections import Counter
        
        # Check for admin preset result
        preset = await get_preset_dice_result(self.round_id)
        if preset:
            logger.info(f"Using admin preset result for round {self.round_id}: {preset}")
            if ',' in str(preset):
                # Multiple dice values provided
                dice = []
                for x in str(preset).split(','):
                    try:
                        dice.append(int(x.strip()))
                    except ValueError:
                        pass
                # Ensure we have exactly 6 dice
                while len(dice) < 6: dice.append(random.randint(1, 6))
                dice = dice[:6]
            else:
                # Single winning number provided - set all 6 dice to it for 100% win
                try:
                    dice = [int(preset)] * 6
                except ValueError:
                    dice = [random.randint(1, 6) for _ in range(6)]
            
            result_str = determine_winning_number(dice)
            return dice, result_str

        # Random generation if no preset
        dice = [random.randint(1, 6) for _ in range(6)]
        result_str = determine_winning_number(dice)
        return dice, result_str

    async def publish_state(self, legacy_type=None):
        now_mono = time.monotonic()
        elapsed_seconds = now_mono - self.start_monotonic
        timer = max(1, int(elapsed_seconds) + 1)
        
        state = {
            "type": legacy_type or "timer",
            "round_id": self.round_id,
            "timer": timer,
            "status": self.status,
            "is_rolling": self.status == "ROLLING",
            "server_time": int(time.time())
        }
        
        if self.status == "RESULT" and hasattr(self, 'last_dice_values') :
            state['dice_values'] = self.last_dice_values
            for i, val in enumerate(self.last_dice_values, 1):
                state[f'dice_{i}'] = val
            state['dice_result'] = self.dice_result
        await self.redis.publish(GAME_ROOM_CHANNEL, payload)

            state['dice_result'] = self.dice_result

        payload = json.dumps(state)
        await self.redis.set(GAME_STATE_KEY, payload, ex=5)
        logger.info(f"Publishing state: round={self.round_id}, timer={timer}, status={self.status}")
        await self.connect_redis()
        lock_id = await self.acquire_lock()
        asyncio.create_task(self.renew_lock(lock_id))

        while True:
            await self.start_new_round()
            
            last_publish_time = 0
            while True:
                now = time.monotonic()
                elapsed = now - self.start_monotonic
                current_timer = int(elapsed) + 1
                
                if current_timer <= BETTING_CLOSE_TIME:
                    new_status = "BETTING"
                elif current_timer <= DICE_ROLL_TIME:
                    new_status = "ROLLING"
                elif current_timer <= ROUND_END_TIME:
                    new_status = "RESULT"
                else:
                    break

                status_changed = (new_status != self.status)
                self.status = new_status
                already_published = False

                if self.status == "ROLLING" and status_changed:
                    logger.info(f"Round {self.round_id}: Rolling started")
                    await self.publish_state(legacy_type="dice_roll")
                    already_published = True
                    last_publish_time = now
                
                if self.status == "RESULT" and status_changed:
                    dice_values, result_str = await self.generate_dice_result()
                    self.dice_result = result_str
                    self.last_dice_values = dice_values
                    logger.info(f"Round {self.round_id}: Result {result_str}")
                    
                    await self.redis.xadd(ROUND_EVENTS_STREAM, {
                        "type": "round_result",
                        "round_id": self.round_id,
                        "dice_values": json.dumps(dice_values),
                        "result": result_str,
                        "end_time": datetime.utcnow().isoformat()
                    })
                    
                    await self.publish_state(legacy_type="dice_result")
                    already_published = True
                    last_publish_time = now

                current_time = time.monotonic()
                time_since_last_publish = current_time - last_publish_time
                
                should_publish = False
                if status_changed and not already_published:
                    should_publish = True
                elif time_since_last_publish >= 0.95:
                    should_publish = True
                
                if should_publish:
                    if current_timer == 1:
                        await self.publish_state(legacy_type="game_start")
                        await self.publish_state(legacy_type="timer")
                    else:
                        await self.publish_state()
                    last_publish_time = time.monotonic()

                await asyncio.sleep(0.1) 

            logger.info(f"Round {self.round_id} completed")
            await self.publish_state(legacy_type="game_end")
            await asyncio.sleep(1)

if __name__ == "__main__":
    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped")
