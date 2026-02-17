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
from game.utils import get_all_game_settings

# Async wrapper for get_all_game_settings (database access)
@sync_to_async
def async_get_all_game_settings():
    """Async wrapper for get_all_game_settings"""
    from django.db import connections
    connections.close_all()
    return get_all_game_settings()

# Configuration
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

GAME_ROOM_CHANNEL = "game_room"
ROUND_EVENTS_STREAM = "round_events_stream"
GAME_STATE_KEY = "current_game_state"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 10  # seconds

# Global settings variables
BETTING_CLOSE_TIME = 30
DICE_ROLL_TIME = 38
DICE_RESULT_TIME = 43
ROUND_END_TIME = 50

# Server Priority Configuration
SERVER_IP = os.getenv('SERVER_IP', 'unknown')
PRIMARY_SERVER_IP = '72.61.254.74'  # Server 3

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
        self.current_settings = {}
        self.is_primary = (SERVER_IP == PRIMARY_SERVER_IP)

    async def connect_redis(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info(f"Connected to Redis at {settings.REDIS_HOST} (Primary: {self.is_primary})")

    async def acquire_lock(self):
        """
        Ensure only one engine runs using Redis SETNX.
        If this is the PRIMARY server (Server 3), it will FORCE take the lock
        from any other server.
        """
        identifier = str(uuid.uuid4())
        while True:
            if self.is_primary:
                # Server 3: Force take the lock
                await self.redis.set(ENGINE_LOCK_KEY, identifier, ex=LOCK_TIMEOUT)
                logger.info(f"PRIMARY Server 3: Forcefully acquired engine lock: {identifier}")
                return identifier
            
            # Other servers: Standard SETNX (only take if free)
            if await self.redis.set(ENGINE_LOCK_KEY, identifier, ex=LOCK_TIMEOUT, nx=True):
                logger.info(f"Standby Server: Acquired engine lock: {identifier}")
                return identifier
            
            logger.warning("Another engine is running, waiting...")
            await asyncio.sleep(5)

    async def renew_lock(self, identifier):
        """Keep the lock alive, but check if Server 3 has taken it back"""
        while True:
            try:
                # Check who holds the lock
                current_holder = await self.redis.get(ENGINE_LOCK_KEY)
                
                # If I am NOT Server 3, and the lock holder changed, I must stop
                if not self.is_primary and current_holder != identifier:
                    logger.warning("PRIMARY Server 3 has taken over. Reverting to standby.")
                    os._exit(0) # Exit and let Docker restart the container in standby mode
                
                await self.redis.expire(ENGINE_LOCK_KEY, LOCK_TIMEOUT)
            except Exception as e:
                logger.error(f"Lock renewal failed: {e}")
            await asyncio.sleep(LOCK_TIMEOUT / 2)

    async def start_new_round(self):
        # Reload game settings each round (they might have changed)
        global BETTING_CLOSE_TIME, DICE_ROLL_TIME, DICE_RESULT_TIME, ROUND_END_TIME
        
        try:
            # Fetch all settings at once to minimize DB calls
            self.current_settings = await async_get_all_game_settings()
            
            BETTING_CLOSE_TIME = int(self.current_settings.get('BETTING_CLOSE_TIME', 30))
            DICE_ROLL_TIME = int(self.current_settings.get('DICE_ROLL_TIME', 38))
            DICE_RESULT_TIME = int(self.current_settings.get('DICE_RESULT_TIME', 43))
            ROUND_END_TIME = int(self.current_settings.get('ROUND_END_TIME', 50))
        except Exception as e:
            logger.error(f"Error loading settings from DB: {e}. Using defaults.")
            # Safe defaults if DB fails
            BETTING_CLOSE_TIME = 30
            DICE_ROLL_TIME = 38
            DICE_RESULT_TIME = 43
            ROUND_END_TIME = 50

        self.round_id = f"R{int(time.time())}"
        self.start_monotonic = time.monotonic()
        self.end_monotonic = self.start_monotonic + ROUND_END_TIME
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
                "round_end_time": ROUND_END_TIME
            })
        }
        await self.redis.xadd(ROUND_EVENTS_STREAM, event)

        # CRITICAL: Clear old round totals from Redis to prevent chips carrying forward
        try:
            await self.redis.delete(f"round_total_bets:{self.round_id}")
            await self.redis.delete(f"round_total_amount:{self.round_id}")
            await self.redis.delete(f"round:{self.round_id}:total_exposure")
            await self.redis.delete(f"round:{self.round_id}:user_exposure")
            await self.redis.delete(f"round:{self.round_id}:bet_count")
            logger.info(f"Cleared Redis stats for new round {self.round_id}")
        except Exception as e:
            logger.error(f"Error clearing Redis stats: {e}")

    async def generate_dice_result(self):
        """Generate dice result, checking for manual override first (Redis or DB)"""
        import random
        from collections import Counter
        from game.models import GameRound
        
        # 1. Check for manual override in Redis (Fastest)
        try:
            manual_result_raw = await self.redis.get("manual_dice_result")
            if manual_result_raw:
                logger.info(f"Manual dice result found in Redis: {manual_result_raw}")
                manual_dice = [int(x.strip()) for x in manual_result_raw.split(",")]
                if len(manual_dice) == 6:
                    await self.redis.delete("manual_dice_result")
                    counts = Counter(manual_dice)
                    winners = sorted([num for num, count in counts.items() if count >= 2])
                    result_str = ",".join(map(str, winners)) if winners else "0"
                    return manual_dice, result_str
        except Exception as e:
            logger.error(f"Error checking manual dice result in Redis: {e}")

        # 2. Check for manual override in Database (Fallback for Admin Panel)
        try:
            def get_db_dice():
                from django.db import connections
                connections.close_all()
                try:
                    r = GameRound.objects.get(round_id=self.round_id)
                    if all(getattr(r, f'dice_{i}') is not None for i in range(1, 7)):
                        return [getattr(r, f'dice_{i}') for i in range(1, 7)]
                    return None
                except GameRound.DoesNotExist:
                    return None
            
            db_dice = await sync_to_async(get_db_dice)()
            if db_dice:
                counts = Counter(db_dice)
                winners = sorted([num for num, count in counts.items() if count >= 2])
                result_str = ",".join(map(str, winners)) if winners else "0"
                return db_dice, result_str
        except Exception as e:
            logger.error(f"Error checking manual dice result in DB: {e}")

        # 3. Fallback to random generation
        dice = [random.randint(1, 6) for _ in range(6)]
        counts = Counter(dice)
        winners = sorted([num for num, count in counts.items() if count >= 2])
        result_str = ",".join(map(str, winners)) if winners else "0"
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
            "dice_result": self.dice_result,
            "is_rolling": self.status == "ROLLING",
            "server_time": int(time.time()),
            "total_round_duration": ROUND_END_TIME,
            "betting_close_time": BETTING_CLOSE_TIME,
            "dice_roll_time": DICE_ROLL_TIME,
            "dice_result_time": DICE_RESULT_TIME
        }
        
        # Merge all settings from the API into the WebSocket message
        if hasattr(self, 'current_settings'):
            state['settings'] = self.current_settings
        
        if self.status == "RESULT" and hasattr(self, 'last_dice_values'):
            state['dice_values'] = self.last_dice_values
            for i, val in enumerate(self.last_dice_values, 1):
                state[f'dice_{i}'] = val
            state['result'] = self.dice_result

        payload = json.dumps(state)
        await self.redis.set(GAME_STATE_KEY, payload, ex=5)
        await self.redis.set('current_round', payload, ex=5)
        
        logger.info(f"Publishing state: round={self.round_id}, timer={timer}, status={self.status}")
        await self.redis.publish(GAME_ROOM_CHANNEL, payload)

    async def run(self):
        await self.connect_redis()
        lock_id = await self.acquire_lock()
        asyncio.create_task(self.renew_lock(lock_id))

        while True:
            await self.start_new_round()
            self.start_monotonic = time.monotonic()
            last_publish_time = 0
            
            while True:
                now = time.monotonic()
                elapsed = now - self.start_monotonic
                current_timer = int(elapsed) + 1
                
                dice_roll_sent = hasattr(self, '_dice_roll_sent') and self._dice_roll_sent
                already_published = False
                
                if current_timer == DICE_ROLL_TIME and not dice_roll_sent:
                    self.status = "ROLLING"
                    await self.publish_state(legacy_type="dice_roll")
                    self._dice_roll_sent = True
                    dice_roll_sent = True
                    already_published = True
                    last_publish_time = now
                
                if current_timer <= BETTING_CLOSE_TIME:
                    new_status = "BETTING"
                elif not dice_roll_sent:
                    if current_timer <= ROUND_END_TIME:
                        new_status = "CLOSED"
                    else:
                        break
                elif current_timer <= DICE_RESULT_TIME:
                    new_status = "ROLLING"
                elif current_timer <= ROUND_END_TIME:
                    new_status = "RESULT"
                else:
                    break

                status_changed = (new_status != self.status)
                if status_changed:
                    self.status = new_status
                
                if self.status == "RESULT" and status_changed:
                    dice_values, result_str = await self.generate_dice_result()
                    self.dice_result = result_str
                    self.last_dice_values = dice_values
                    await self.redis.xadd(ROUND_EVENTS_STREAM, {
                        "type": "round_result",
                        "round_id": self.round_id,
                        "dice_values": json.dumps(dice_values),
                        "result": result_str,
                        "end_time": datetime.utcnow().isoformat()
                    })
                    await self.publish_state(legacy_type="dice_result")
                    await self.redis.delete('last_round_results_cache')
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

            await self.publish_state(legacy_type="game_end")
            try:
                await self.redis.delete(f"round:{self.round_id}:total_exposure")
                await self.redis.delete(f"round:{self.round_id}:user_exposure")
                await self.redis.delete(f"round:{self.round_id}:bet_count")
            except Exception as e:
                logger.error(f"Error clearing final exposure stats: {e}")

            await asyncio.sleep(1)

if __name__ == "__main__":
    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped")
