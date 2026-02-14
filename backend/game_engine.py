import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime
import redis.asyncio as redis

# Configuration
REDIS_URL = "redis://localhost:6379/0"
GAME_UPDATE_CHANNEL = "game_updates"
SETTLE_STREAM = "settle_stream"
GAME_STATE_KEY = "current_game_state"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 10  # seconds

# Game Settings (could be loaded from Redis/Env)
BETTING_DURATION = 30
DICE_ROLL_DURATION = 20
RESULT_DISPLAY_DURATION = 20
TOTAL_ROUND_DURATION = BETTING_DURATION + DICE_ROLL_DURATION + RESULT_DISPLAY_DURATION

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GameEngine")

class GameEngine:
    def __init__(self):
        self.redis = None
        self.round_id = None
        self.timer = TOTAL_ROUND_DURATION
        self.status = "WAITING"
        self.dice_result = None

    async def connect_redis(self):
        self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Connected to Redis")

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
            await self.redis.expire(ENGINE_LOCK_KEY, LOCK_TIMEOUT)
            await asyncio.sleep(LOCK_TIMEOUT / 2)

    async def start_new_round(self):
        self.round_id = f"R{int(time.time())}"
        self.timer = TOTAL_ROUND_DURATION
        self.status = "BETTING"
        self.dice_result = None
        logger.info(f"New Round Started: {self.round_id}")

    def generate_dice_result(self):
        # Rule: 6 dice, winner if number appears 2+ times
        dice = [random.randint(1, 6) for _ in range(6)]
        from collections import Counter
        counts = Counter(dice)
        winners = sorted([num for num, count in counts.items() if count >= 2])
        result = ",".join(map(str, winners)) if winners else "0"
        return dice, result

    async def publish_state(self):
        state = {
            "round_id": self.round_id,
            "timer": self.timer,
            "status": self.status,
            "dice_result": self.dice_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        # Store in Redis for instant state recovery
        await self.redis.set(GAME_STATE_KEY, json.dumps(state))
        # Publish to Pub/Sub for WebSockets
        await self.redis.publish(GAME_UPDATE_CHANNEL, json.dumps(state))

    async def push_settlement(self, dice_values, result):
        job = {
            "round_id": self.round_id,
            "dice_values": json.dumps(dice_values),
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        # Push to Redis Stream for background workers to process payouts
        await self.redis.xadd(SETTLE_STREAM, job)
        logger.info(f"Pushed settlement job for round {self.round_id}")

    async def run(self):
        await self.connect_redis()
        lock_id = await self.acquire_lock()
        
        # Start lock renewal in background
        asyncio.create_task(self.renew_lock(lock_id))

        while True:
            await self.start_new_round()
            
            while self.timer > 0:
                # Update status based on timer
                if self.timer > (DICE_ROLL_DURATION + RESULT_DISPLAY_DURATION):
                    self.status = "BETTING"
                elif self.timer > RESULT_DISPLAY_DURATION:
                    self.status = "CLOSED"
                else:
                    if self.status != "RESULT":
                        # Transition to RESULT state: generate dice
                        self.status = "RESULT"
                        dice_values, result = self.generate_dice_result()
                        self.dice_result = result
                        await self.push_settlement(dice_values, result)
                
                await self.publish_state()
                await asyncio.sleep(1)
                self.timer -= 1

            # Round End
            self.status = "COMPLETED"
            await self.publish_state()
            await asyncio.sleep(1) # Brief pause before next round

if __name__ == "__main__":
    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped")
