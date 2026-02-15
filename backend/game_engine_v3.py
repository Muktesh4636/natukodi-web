import asyncio
import json
import logging
import random
import time
import uuid
import redis.asyncio as redis
from datetime import datetime, timezone

# Configuration - No Django needed!
REDIS_HOST = "72.62.226.41"
REDIS_PORT = 6379
REDIS_PASSWORD = "Gunduata@123"
REDIS_DB = 0

GAME_UPDATE_CHANNEL = "game_updates"
SETTLE_STREAM = "settle_stream"
GAME_STATE_KEY = "current_game_state"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 5  # seconds
LOCK_REFRESH_INTERVAL = 2  # seconds

# Game Settings
BETTING_DURATION = 30
DICE_ROLL_DURATION = 20
RESULT_DISPLAY_DURATION = 20
TOTAL_ROUND_DURATION = BETTING_DURATION + DICE_ROLL_DURATION + RESULT_DISPLAY_DURATION

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GameEngine")

# Lua script for atomic lock release
RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

def generate_dice_result():
    """Generate six random dice values and determine winning number(s)."""
    dice_values = [random.randint(1, 6) for _ in range(6)]
    # Count occurrences
    counts = {}
    for val in dice_values:
        counts[val] = counts.get(val, 0) + 1
    
    # Find numbers that appear 2+ times
    winners = sorted([num for num, count in counts.items() if count >= 2])
    result = ",".join(map(str, winners)) if winners else "0"
    
    return dice_values, result

class GameEngine:
    def __init__(self):
        self.redis = None
        self.round_id = None
        self.timer = TOTAL_ROUND_DURATION
        self.status = "WAITING"
        self.dice_result = None
        self.dice_values = None
        self.instance_id = str(uuid.uuid4())
        self.is_leader = False

    async def connect_redis(self):
        """Connect to Redis"""
        redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        self.redis = redis.from_url(redis_url, decode_responses=True)
        logger.info(f"Connected to Redis. Instance ID: {self.instance_id}")

    async def acquire_lock(self):
        """Try to acquire the leader lock"""
        return await self.redis.set(ENGINE_LOCK_KEY, self.instance_id, ex=LOCK_TIMEOUT, nx=True)

    async def refresh_lock(self):
        """Refresh the leader lock. If it fails, we are no longer the leader."""
        val = await self.redis.get(ENGINE_LOCK_KEY)
        if val == self.instance_id:
            return await self.redis.expire(ENGINE_LOCK_KEY, LOCK_TIMEOUT)
        return False

    async def release_lock(self):
        """Release the lock using Lua script for atomicity"""
        try:
            await self.redis.eval(RELEASE_LOCK_LUA, 1, ENGINE_LOCK_KEY, self.instance_id)
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

    async def start_new_round(self):
        """Start a new game round"""
        self.round_id = f"R{int(time.time())}"
        self.timer = TOTAL_ROUND_DURATION
        self.status = "BETTING"
        self.dice_result = None
        self.dice_values = None
        logger.info(f"New Round Started: {self.round_id}")

    async def publish_state(self):
        """Publish game state to Redis (both JSON and MessagePack)"""
        state = {
            "round_id": self.round_id,
            "timer": self.timer,
            "status": self.status,
            "dice_result": self.dice_result,
            "dice_values": self.dice_values,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # JSON for compatibility
            state_json = json.dumps(state)
            await self.redis.set(GAME_STATE_KEY, state_json, ex=120)
            await self.redis.publish(GAME_UPDATE_CHANNEL, state_json)
            
            # MessagePack for performance (binary)
            try:
                import msgpack
                state_msgpack = msgpack.packb(state)
                await self.redis.set(f"{GAME_STATE_KEY}_msgpack", state_msgpack, ex=120)
                await self.redis.publish(f"{GAME_UPDATE_CHANNEL}_msgpack", state_msgpack)
            except ImportError:
                logger.warning("msgpack not installed, skipping binary format")
            
            # Also update round_timer for compatibility
            await self.redis.set("round_timer", str(self.timer), ex=120)
            
        except Exception as e:
            logger.error(f"Error publishing state: {e}")

    async def push_settlement(self, dice_values, result):
        """Push settlement job to Redis Stream for workers"""
        try:
            job = {
                "round_id": self.round_id,
                "dice_values": json.dumps(dice_values),
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.redis.xadd(SETTLE_STREAM, job)
            logger.info(f"Pushed settlement job for round {self.round_id}: {result}")
        except Exception as e:
            logger.error(f"Error pushing settlement: {e}")

    async def run_game_loop(self):
        """The actual game logic. Only runs when we are leader."""
        logger.info("Starting game loop as LEADER")
        
        while self.is_leader:
            try:
                await self.start_new_round()
                
                while self.timer > 0 and self.is_leader:
                    # Determine status based on timer
                    if self.timer > (DICE_ROLL_DURATION + RESULT_DISPLAY_DURATION):
                        self.status = "BETTING"
                    elif self.timer > RESULT_DISPLAY_DURATION:
                        self.status = "CLOSED"
                    else:
                        # RESULT phase - generate dice if not already done
                        if self.status != "RESULT":
                            self.status = "RESULT"
                            self.dice_values, self.dice_result = generate_dice_result()
                            await self.push_settlement(self.dice_values, self.dice_result)
                            logger.info(f"Dice rolled: {self.dice_values} -> Result: {self.dice_result}")
                    
                    # Publish state every second
                    await self.publish_state()
                    
                    # Sleep 1 second, checking lock every 0.1s
                    for _ in range(10):
                        await asyncio.sleep(0.1)
                        if not self.is_leader:
                            logger.warning("Lost leadership during game loop")
                            break
                    
                    self.timer -= 1
                
                # Round completed
                if self.is_leader:
                    self.status = "COMPLETED"
                    await self.publish_state()
                    logger.info(f"Round {self.round_id} completed")
                    await asyncio.sleep(1)  # Brief pause before next round
                    
            except Exception as e:
                logger.error(f"Error in game loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def run(self):
        """Main run loop with leader election"""
        await self.connect_redis()
        
        logger.info("Game Engine started, waiting for leadership...")
        
        while True:
            try:
                if not self.is_leader:
                    # Try to become leader
                    if await self.acquire_lock():
                        self.is_leader = True
                        logger.info("Became LEADER")
                        
                        # Start game loop task
                        loop_task = asyncio.create_task(self.run_game_loop())
                        
                        # Lock refresher - runs concurrently with game loop
                        refresh_task = asyncio.create_task(self.refresh_lock_loop())
                        
                        # Wait for either task to complete (they run concurrently)
                        done, pending = await asyncio.wait(
                            [loop_task, refresh_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel remaining tasks
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                        
                        # If we lost leadership, cleanup
                        if not self.is_leader:
                            logger.warning("Lost leadership, stopping game loop")
                            loop_task.cancel()
                            try:
                                await loop_task
                            except asyncio.CancelledError:
                                pass
                    else:
                        # Not leader, wait and try again
                        await asyncio.sleep(2)
                else:
                    # Should not reach here
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(2)

    async def refresh_lock_loop(self):
        """Continuously refresh the lock while we are leader"""
        while self.is_leader:
            await asyncio.sleep(LOCK_REFRESH_INTERVAL)
            if not await self.refresh_lock():
                self.is_leader = False
                logger.warning("Lost LEADER lock!")
                break

if __name__ == "__main__":
    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
