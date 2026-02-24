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
from django.db import connections
from asgiref.sync import sync_to_async
from game.utils import get_game_setting, get_all_game_settings

# Async wrapper for get_all_game_settings (database access)
@sync_to_async
def async_get_all_game_settings():
    """Async wrapper for get_all_game_settings"""
    connections.close_all() # Ensure fresh connection
    return get_all_game_settings()

# Configuration
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

GAME_ROOM_CHANNEL = "game_room"
ROUND_EVENTS_STREAM = "round_events_stream"
GAME_STATE_KEY = "current_game_state"
CURRENT_ROUND_ID_KEY = "current_round_id"
CURRENT_STATUS_KEY = "current_status"
CURRENT_END_TIME_KEY = "current_end_time"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 10  # seconds

# Priority Failover Configuration
SERVER_ID = os.getenv('SERVER_ID', 'unknown')
PRIMARY_SERVER_ID = '74'

# Game time points (seconds from round start) - loaded from database settings
BETTING_CLOSE_TIME = 30  # When betting closes
DICE_ROLL_TIME = 38      # When dice roll animation starts
DICE_RESULT_TIME = 43    # When final result is shown
ROUND_END_TIME = 60      # When round ends and starts new one

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
        logger.info(f"Connected to Redis at {settings.REDIS_HOST} (Server ID: {SERVER_ID})")

    async def acquire_lock(self):
        """Ensure only one engine runs using Redis SETNX with Priority Logic"""
        while True:
            current_lock = await self.redis.get(ENGINE_LOCK_KEY)
            
            # PRIORITY LOGIC:
            # 1. If I am the Primary (74), I always try to take the lock
            if SERVER_ID == PRIMARY_SERVER_ID:
                if current_lock and current_lock != SERVER_ID:
                    logger.info(f"Primary server {SERVER_ID} detected lock held by {current_lock}. Reclaiming...")
                    await self.redis.delete(ENGINE_LOCK_KEY)
                
                if await self.redis.set(ENGINE_LOCK_KEY, SERVER_ID, ex=LOCK_TIMEOUT, nx=True):
                    logger.info(f"Primary server {SERVER_ID} acquired engine lock.")
                    return SERVER_ID
            
            # 2. If I am NOT the Primary, I only take the lock if it's free or held by another standby
            else:
                if current_lock == PRIMARY_SERVER_ID:
                    logger.warning(f"Standby server {SERVER_ID} detected Primary ({PRIMARY_SERVER_ID}) is active. Waiting...")
                else:
                    # Lock is free or held by another standby, try to acquire
                    if await self.redis.set(ENGINE_LOCK_KEY, SERVER_ID, ex=LOCK_TIMEOUT, nx=True):
                        logger.info(f"Standby server {SERVER_ID} acquired engine lock.")
                        return SERVER_ID
            
            await asyncio.sleep(5)

    async def renew_lock(self, identifier):
        """Keep the lock alive, but yield if a higher priority server wants it"""
        while True:
            try:
                # Check if someone else (like Primary) took the lock from us
                current_lock = await self.redis.get(ENGINE_LOCK_KEY)
                if current_lock != SERVER_ID:
                    logger.warning(f"Lock lost! Held by {current_lock}. Stopping engine...")
                    os._exit(1) # Exit and let Docker restart us (we will then wait in acquire_lock)
                
                await self.redis.expire(ENGINE_LOCK_KEY, LOCK_TIMEOUT)
            except Exception as e:
                logger.error(f"Lock renewal failed: {e}")
            await asyncio.sleep(LOCK_TIMEOUT / 2)

    async def start_new_round(self):
        # Reload game settings each round
        global BETTING_CLOSE_TIME, DICE_ROLL_TIME, DICE_RESULT_TIME, ROUND_END_TIME
        
        old_round_id = self.round_id
        
        try:
            all_settings = await async_get_all_game_settings()
            BETTING_CLOSE_TIME = all_settings.get('BETTING_CLOSE_TIME', 30)
            DICE_ROLL_TIME = all_settings.get('DICE_ROLL_TIME', 38)
            DICE_RESULT_TIME = all_settings.get('DICE_RESULT_TIME', 43)
            ROUND_END_TIME = all_settings.get('ROUND_END_TIME', 60)
            self.current_settings = all_settings
        except Exception as e:
            logger.error(f"Error reloading settings: {e}")
        
        self.round_id = f"R{int(time.time())}"
        self.start_monotonic = time.monotonic()
        self.status = "BETTING"
        self.dice_result = None
        if hasattr(self, '_dice_roll_sent'):
            delattr(self, '_dice_roll_sent')
        
        logger.info(f"New Round Started: {self.round_id}")
        
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

        try:
            if old_round_id:
                await self.redis.delete(f"round_total_bets:{old_round_id}")
                await self.redis.delete(f"round_total_amount:{old_round_id}")
                logger.info(f"Cleaned up Redis stats for {old_round_id}")
        except Exception as e:
            logger.error(f"Error managing Redis cleanup: {e}")

    async def generate_dice_result(self):
        import random
        from collections import Counter
        from game.models import GameRound
        
        try:
            manual_result_raw = await self.redis.get("manual_dice_result")
            if manual_result_raw:
                manual_dice = [int(x.strip()) for x in manual_result_raw.split(",")]
                if len(manual_dice) == 6:
                    await self.redis.delete("manual_dice_result")
                    counts = Counter(manual_dice)
                    winners = sorted([num for num, count in counts.items() if count >= 2])
                    result_str = ",".join(map(str, winners)) if winners else "0"
                    return manual_dice, result_str
        except Exception as e:
            logger.error(f"Error checking manual result: {e}")

        dice_values = [random.randint(1, 6) for _ in range(6)]
        counts = Counter(dice_values)
        winners = sorted([num for num, count in counts.items() if count >= 2])
        result_str = ",".join(map(str, winners)) if winners else "0"
        return dice_values, result_str

    async def publish_state(self, legacy_type="timer"):
        elapsed = time.monotonic() - self.start_monotonic
        timer = int(elapsed) + 1
        end_timestamp = int(time.time() + (ROUND_END_TIME - timer))

        state = {
            "type": legacy_type,
            "round_id": self.round_id,
            "timer": timer,
            "status": self.status,
            "dice_result": self.dice_result,
            "is_rolling": self.status == "ROLLING",
            "server_time": int(time.time()),
            "end_time": end_timestamp,
            "total_round_duration": ROUND_END_TIME,
            "server_id": SERVER_ID
        }
        
        if hasattr(self, 'current_settings'):
            state['settings'] = self.current_settings
        
        if self.status == "RESULT" and hasattr(self, 'last_dice_values'):
            state['dice_values'] = self.last_dice_values
            state['dice_result'] = self.dice_result

        payload = json.dumps(state)
        pipe = self.redis.pipeline()
        pipe.set(GAME_STATE_KEY, payload, ex=60)
        pipe.set('current_round', payload, ex=60)
        pipe.set(CURRENT_ROUND_ID_KEY, str(self.round_id), ex=60)
        pipe.set(CURRENT_STATUS_KEY, str(self.status), ex=60)
        await pipe.execute()
        
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
                    already_published = True
                    last_publish_time = now

                current_time = time.monotonic()
                if status_changed and not already_published:
                    await self.publish_state()
                    last_publish_time = current_time
                elif current_time - last_publish_time >= 0.95:
                    await self.publish_state()
                    last_publish_time = current_time
                
                await asyncio.sleep(0.1) 

            await self.publish_state(legacy_type="game_end")
            await asyncio.sleep(1)

if __name__ == "__main__":
    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped")
