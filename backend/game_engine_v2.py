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

# Configuration
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

GAME_ROOM_CHANNEL = "game_room"
ROUND_EVENTS_STREAM = "round_events_stream"
GAME_STATE_KEY = "current_game_state"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 10  # seconds

# Game Durations (from settings or defaults)
BETTING_DURATION = 30
DICE_ROLL_DURATION = 5
RESULT_DISPLAY_DURATION = 10
TOTAL_ROUND_DURATION = BETTING_DURATION + DICE_ROLL_DURATION + RESULT_DISPLAY_DURATION

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
        self.round_id = f"R{int(time.time())}"
        self.start_monotonic = time.monotonic()
        self.end_monotonic = self.start_monotonic + TOTAL_ROUND_DURATION
        self.status = "BETTING"
        self.dice_result = None
        
        logger.info(f"New Round Started: {self.round_id}")
        
        # Push event to stream for DB worker
        event = {
            "type": "round_start",
            "round_id": self.round_id,
            "start_time": datetime.utcnow().isoformat(),
            "durations": json.dumps({
                "betting": BETTING_DURATION,
                "roll": DICE_ROLL_DURATION,
                "result": RESULT_DISPLAY_DURATION
            })
        }
        await self.redis.xadd(ROUND_EVENTS_STREAM, event)

    def generate_dice_result(self):
        import random
        from collections import Counter
        dice = [random.randint(1, 6) for _ in range(6)]
        counts = Counter(dice)
        winners = sorted([num for num, count in counts.items() if count >= 2])
        result_str = ",".join(map(str, winners)) if winners else "0"
        return dice, result_str

    async def publish_state(self, timer_val):
        state = {
            "type": "timer", # Match consumer expectation
            "round_id": self.round_id,
            "timer": timer_val,
            "status": self.status,
            "dice_result": self.dice_result,
            "is_rolling": self.status == "ROLLING",
            "timestamp": datetime.utcnow().isoformat()
        }
        payload = json.dumps(state)
        # Store for instant recovery
        await self.redis.set(GAME_STATE_KEY, payload)
        # Direct Pub/Sub for high speed
        await self.redis.publish(GAME_ROOM_CHANNEL, payload)

    async def run(self):
        await self.connect_redis()
        lock_id = await self.acquire_lock()
        asyncio.create_task(self.renew_lock(lock_id))

        while True:
            await self.start_new_round()
            
            while True:
                now = time.monotonic()
                elapsed = now - self.start_monotonic
                remaining = max(0, int(TOTAL_ROUND_DURATION - elapsed))
                
                # Update status based on elapsed time
                if elapsed < BETTING_DURATION:
                    self.status = "BETTING"
                elif elapsed < (BETTING_DURATION + DICE_ROLL_DURATION):
                    if self.status != "ROLLING":
                        self.status = "ROLLING"
                        logger.info(f"Round {self.round_id}: Rolling started")
                elif elapsed < TOTAL_ROUND_DURATION:
                    if self.status != "RESULT":
                        self.status = "RESULT"
                        dice_values, result_str = self.generate_dice_result()
                        self.dice_result = result_str
                        logger.info(f"Round {self.round_id}: Result {result_str}")
                        
                        # Push settlement/end event to stream
                        await self.redis.xadd(ROUND_EVENTS_STREAM, {
                            "type": "round_result",
                            "round_id": self.round_id,
                            "dice_values": json.dumps(dice_values),
                            "result": result_str,
                            "end_time": datetime.utcnow().isoformat()
                        })
                else:
                    break # Round finished

                await self.publish_state(remaining)
                # High-frequency check (0.2s) to ensure no drift, but only publish every 1s roughly
                # Or just publish every 0.2s for super smooth UI if bandwidth allows
                await asyncio.sleep(0.5) 

            logger.info(f"Round {self.round_id} completed")
            await asyncio.sleep(1) # Gap between rounds

if __name__ == "__main__":
    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped")
