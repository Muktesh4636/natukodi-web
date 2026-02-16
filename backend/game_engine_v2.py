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
from game.utils import get_game_setting

# Async wrapper for get_game_setting (database access)
@sync_to_async
def async_get_game_setting(key, default):
    """Async wrapper for get_game_setting"""
    return get_game_setting(key, default)

# Configuration
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

GAME_ROOM_CHANNEL = "game_room"
ROUND_EVENTS_STREAM = "round_events_stream"
GAME_STATE_KEY = "current_game_state"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 10  # seconds

# Game time points (seconds from round start) - loaded from database settings
# These define when phases change, timer counts UP from 1
# Default values (will be reloaded from DB at start of each round)
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
        # Reload game settings each round (they might have changed)
        global BETTING_CLOSE_TIME, DICE_ROLL_TIME, DICE_RESULT_TIME, ROUND_END_TIME
        global BETTING_DURATION, DICE_ROLL_DURATION, RESULT_DISPLAY_DURATION, TOTAL_ROUND_DURATION
        
        # Use async wrapper for database access
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
        # Reset dice_roll sent flag for new round
        if hasattr(self, '_dice_roll_sent'):
            delattr(self, '_dice_roll_sent')
        
        logger.info(f"New Round Started: {self.round_id} | Betting: 1-{BETTING_CLOSE_TIME}s | Closed: {BETTING_CLOSE_TIME+1}-{DICE_ROLL_TIME-1}s | Rolling: {DICE_ROLL_TIME}-{DICE_RESULT_TIME}s | Result: {DICE_RESULT_TIME+1}-{ROUND_END_TIME}s")
        
        # Push event to stream for DB worker
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

        # CRITICAL: Clear old round totals from Redis to prevent chips carrying forward
        try:
            # Delete legacy keys
            await self.redis.delete(f"round_total_bets:{self.round_id}")
            await self.redis.delete(f"round_total_amount:{self.round_id}")
            # Also clear exposure keys for this round just in case
            await self.redis.delete(f"round:{self.round_id}:total_exposure")
            await self.redis.delete(f"round:{self.round_id}:bet_count")
            logger.info(f"Cleared Redis stats for new round {self.round_id}")
        except Exception as e:
            logger.error(f"Error clearing Redis stats: {e}")

    def generate_dice_result(self):
        import random
        from collections import Counter
        dice = [random.randint(1, 6) for _ in range(6)]
        counts = Counter(dice)
        winners = sorted([num for num, count in counts.items() if count >= 2])
        result_str = ",".join(map(str, winners)) if winners else "0"
        return dice, result_str

    async def publish_state(self, legacy_type=None):
        # Calculate elapsed time from round start (counts UP from 1)
        now_mono = time.monotonic()
        elapsed_seconds = now_mono - self.start_monotonic
        timer = max(1, int(elapsed_seconds) + 1)  # Timer counts UP from 1
        
        # Calculate when the CURRENT phase ends (for end_time field)
        if self.status == "BETTING":
            phase_end_time = BETTING_CLOSE_TIME
        elif self.status == "ROLLING":
            phase_end_time = DICE_ROLL_TIME
        else: # RESULT
            phase_end_time = DICE_RESULT_TIME
            
        # Calculate remaining time until phase end (for end_time timestamp)
        phase_end_mono = self.start_monotonic + phase_end_time
        remaining_seconds = max(0, phase_end_mono - now_mono)
        end_timestamp = int(time.time() + remaining_seconds)

        state = {
            "type": legacy_type or "timer",
            "round_id": self.round_id,
            "timer": timer,  # Counts UP from 1 (elapsed time + 1)
            "status": self.status,
            "dice_result": self.dice_result,
            "is_rolling": self.status == "ROLLING",
            "server_time": int(time.time())
        }
        
        # Add dice values if in RESULT phase
        if self.status == "RESULT" and hasattr(self, 'last_dice_values'):
            state['dice_values'] = self.last_dice_values
            for i, val in enumerate(self.last_dice_values, 1):
                state[f'dice_{i}'] = val
            state['result'] = self.dice_result

        payload = json.dumps(state)
        # Store for instant recovery (only current round)
        # Set expiration to 5 seconds so it disappears if engine crashes
        await self.redis.set(GAME_STATE_KEY, payload, ex=5)
        # Direct Pub/Sub for high speed (only publish current round)
        # Note: We publish ONE message per update to avoid duplicates
        # The game_state message contains all necessary information including timer
        logger.info(f"Publishing state: round={self.round_id}, timer={timer}, status={self.status}")
        await self.redis.publish(GAME_ROOM_CHANNEL, payload)

    async def run(self):
        await self.connect_redis()
        lock_id = await self.acquire_lock()
        asyncio.create_task(self.renew_lock(lock_id))

        while True:
            await self.start_new_round()
            
            last_publish_time = 0
            while True:
                now = time.monotonic()
                elapsed = now - self.start_monotonic
                current_timer = int(elapsed) + 1  # Timer counts UP from 1
                
                # Update status based on timer value (using configured time points)
                # Status flow: BETTING -> CLOSED -> ROLLING (when dice_roll sent) -> RESULT
                
                # Check if dice_roll has been sent
                dice_roll_sent = hasattr(self, '_dice_roll_sent') and self._dice_roll_sent
                
                # Track if we already published due to status change
                already_published = False
                
                # Send dice_roll message at the EXACT DICE_ROLL_TIME FIRST (before status check)
                if current_timer == DICE_ROLL_TIME and not dice_roll_sent:
                    logger.info(f"Round {self.round_id}: Sending dice_roll at timer {current_timer} (DICE_ROLL_TIME={DICE_ROLL_TIME})")
                    # Change status to ROLLING when dice_roll message is sent
                    self.status = "ROLLING"
                    await self.publish_state(legacy_type="dice_roll")
                    self._dice_roll_sent = True
                    dice_roll_sent = True  # Update local variable
                    already_published = True
                    last_publish_time = now  # Update publish time to prevent immediate duplicate
                    logger.info(f"Round {self.round_id}: Status set to ROLLING after dice_roll sent")
                
                # Determine new status based on timer and dice_roll state
                if current_timer <= BETTING_CLOSE_TIME:
                    new_status = "BETTING"
                elif not dice_roll_sent:
                    # Before dice_roll is sent: Status is CLOSED
                    if current_timer <= ROUND_END_TIME:
                        new_status = "CLOSED"
                    else:
                        break # Round finished
                elif current_timer <= DICE_RESULT_TIME:
                    # After dice_roll message is sent: Status is ROLLING
                    new_status = "ROLLING"
                elif current_timer <= ROUND_END_TIME:
                    new_status = "RESULT"
                else:
                    break # Round finished

                # If status changed, update and publish immediately
                status_changed = (new_status != self.status)
                if status_changed:
                    self.status = new_status
                    logger.info(f"Round {self.round_id}: Status changed to {self.status} at timer {current_timer}")
                
                if self.status == "RESULT" and status_changed:
                    dice_values, result_str = self.generate_dice_result()
                    self.dice_result = result_str
                    self.last_dice_values = dice_values
                    logger.info(f"Round {self.round_id}: Result {result_str}")
                    
                    # Push settlement/end event to stream
                    await self.redis.xadd(ROUND_EVENTS_STREAM, {
                        "type": "round_result",
                        "round_id": self.round_id,
                        "dice_values": json.dumps(dice_values),
                        "result": result_str,
                        "end_time": datetime.utcnow().isoformat()
                    })
                    
                    # Publish legacy dice_result message
                    await self.publish_state(legacy_type="dice_result")
                    already_published = True
                    last_publish_time = now  # Update publish time to prevent immediate duplicate

                # Publish state every 1s OR on status change (but not if already published)
                # CRITICAL: Check time difference to prevent duplicate publishes
                # Use current time again to ensure accuracy after async operations
                current_time = time.monotonic()
                time_since_last_publish = current_time - last_publish_time
                
                # Only publish if:
                # 1. Status changed AND we haven't already published for this status change, OR
                # 2. At least 0.95 seconds have passed since last publish (slightly less than 1.0 to account for timing precision)
                should_publish = False
                if status_changed and not already_published:
                    should_publish = True
                elif time_since_last_publish >= 0.95:  # 0.95s threshold to prevent duplicates
                    should_publish = True
                
                if should_publish:
                    # If it's the start of a new round (timer=1), send TWO messages:
                    # 1. type: "game_start"
                    # 2. type: "timer"
                    if current_timer == 1:
                        await self.publish_state(legacy_type="game_start")
                        await self.publish_state(legacy_type="timer")
                    else:
                        # For all other seconds, just send the standard "timer" message
                        await self.publish_state()
                    
                    last_publish_time = time.monotonic()  # Use fresh monotonic time after publish

                # High-frequency check (0.1s) to ensure status changes are caught immediately
                await asyncio.sleep(0.1) 

            logger.info(f"Round {self.round_id} completed")
            # Send game_end message (only once, no duplicates)
            await self.publish_state(legacy_type="game_end")
            await asyncio.sleep(1) # Gap between rounds

if __name__ == "__main__":
    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped")
