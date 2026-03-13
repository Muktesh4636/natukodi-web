import asyncio
import json
import logging
import os
import random
import time
import uuid
import redis.asyncio as redis
from datetime import datetime, timezone

try:
    from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
except ImportError:
    RedisConnectionError = ConnectionError
    RedisTimeoutError = TimeoutError

# Configuration - use env so all servers point to Redis on 74
REDIS_HOST = os.environ.get("REDIS_HOST", "72.61.254.74")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "Gunduata@123")
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

# Standby mode: when True, only try to become leader when primary's state is stale (primary on 74 stopped).
# Set STANDBY_MODE=1 on servers 71 and 41; leave unset on 74 so 74 is the primary.
STANDBY_MODE = os.environ.get("STANDBY_MODE", "").lower() in ("1", "true", "yes")
STALE_THRESHOLD_SEC = 15  # If no state update for this long, consider primary dead and take over.

GAME_UPDATE_CHANNEL = "game_updates"
GAME_ROOM_CHANNEL = "game_room"  # WebSocket consumer subscribes to this
SETTLE_STREAM = "settle_stream"
ROUND_EVENTS_STREAM = "round_events_stream"
GAME_STATE_KEY = "current_game_state"
# Legacy hot keys used by high-performance bet placement endpoints (views.py / consumers.py)
CURRENT_ROUND_ID_KEY = "current_round_id"
CURRENT_STATUS_KEY = "current_status"
CURRENT_END_TIME_KEY = "current_end_time"
ENGINE_LOCK_KEY = "game_engine_lock"
LOCK_TIMEOUT = 5  # seconds
LOCK_REFRESH_INTERVAL = 2  # seconds

# Defaults for game settings; real values from Django GameSettings (get_round_settings)
DEFAULT_BETTING_CLOSE_TIME = 30
DEFAULT_DICE_ROLL_TIME = 19
DEFAULT_DICE_RESULT_TIME = 51
DEFAULT_ROUND_END_TIME = 80


def get_round_settings(previous=None):
    """
    Load timer phase settings from Django GameSettings (same source as /api/game/settings/).

    Important: If DB lookups intermittently fail, DO NOT fall back to settings.GAME_SETTINGS
    (which can differ from DB) — keep the last known-good settings instead.
    Call after django.setup().
    """
    base = dict(previous or {})
    base.setdefault("betting_close_time", DEFAULT_BETTING_CLOSE_TIME)
    base.setdefault("dice_roll_time", DEFAULT_DICE_ROLL_TIME)
    base.setdefault("dice_result_time", DEFAULT_DICE_RESULT_TIME)
    base.setdefault("round_end_time", DEFAULT_ROUND_END_TIME)

    # Retry once on transient DB errors.
    for attempt in range(2):
        try:
            from game.models import GameSettings as _GameSettings

            def _read_int(key, fallback):
                raw = _GameSettings.objects.filter(key=key).values_list("value", flat=True).first()
                if raw is None:
                    return fallback
                try:
                    return int(float(raw))
                except Exception:
                    return fallback

            out = {
                "betting_close_time": _read_int("BETTING_CLOSE_TIME", base["betting_close_time"]),
                "dice_roll_time": _read_int("DICE_ROLL_TIME", base["dice_roll_time"]),
                "dice_result_time": _read_int("DICE_RESULT_TIME", base["dice_result_time"]),
                "round_end_time": _read_int("ROUND_END_TIME", base["round_end_time"]),
            }
            logger.info(
                "Game settings resolved: ROUND_END=%s, BETTING_CLOSE=%s, DICE_ROLL=%s, DICE_RESULT=%s",
                out["round_end_time"],
                out["betting_close_time"],
                out["dice_roll_time"],
                out["dice_result_time"],
            )
            return out
        except Exception as e:
            if attempt == 0:
                time.sleep(0.5)
                continue
            logger.warning(f"Could not load game settings from DB ({e}); keeping previous/defaults: {base}")
            return base
    return base


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
    """Fallback: pure random dice."""
    dice_values = [random.randint(1, 6) for _ in range(6)]
    counts = {}
    for val in dice_values:
        counts[val] = counts.get(val, 0) + 1
    winners = sorted([num for num, count in counts.items() if count >= 2])
    result = ",".join(map(str, winners)) if winners else "0"
    return dice_values, result


async def generate_smart_dice_result(redis_client, round_id):
    """Smart dice — uses player journey states to decide outcome."""
    try:
        import sys
        import os
        # Allow import from project root
        project_root = os.path.dirname(os.path.abspath(__file__))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from smart_dice_engine import generate_smart_dice_async
        return await generate_smart_dice_async(redis_client, round_id)
    except Exception as exc:
        logger.warning(f"Smart dice unavailable ({exc}), falling back to random")
        return generate_dice_result()

class GameEngine:
    def __init__(self):
        self.redis = None
        self.round_id = None
        self.timer = 0
        self.status = "WAITING"
        self.dice_result = None
        self.dice_values = None
        self.instance_id = str(uuid.uuid4())
        self.is_leader = False
        self.settings = get_round_settings()  # betting_close_time, dice_roll_time, dice_result_time, round_end_time
        # Per-round one-shot WS events (avoid spamming on every tick)
        self._sent_dice_roll = False
        self._sent_dice_result = False
        self._sent_game_end = False
        self._sent_game_start = False

    async def connect_redis(self):
        """Connect to Redis. On the Redis host (e.g. 74), container→host IP often fails; fallback to Docker service name 'redis'."""
        redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5)
            await self.redis.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}. Instance ID: {self.instance_id}")
            return
        except (RedisConnectionError, RedisTimeoutError, ConnectionError, TimeoutError, OSError) as e:
            try:
                if getattr(self, "redis", None):
                    await self.redis.aclose()
            except Exception:
                pass
            if REDIS_HOST and REDIS_HOST.replace(".", "").isdigit():
                fallback = "redis"
                logger.warning(f"Redis connect to {REDIS_HOST} failed ({e}), trying Docker service name '{fallback}'")
                redis_url_fallback = f"redis://:{REDIS_PASSWORD}@{fallback}:{REDIS_PORT}/{REDIS_DB}"
                self.redis = redis.from_url(redis_url_fallback, decode_responses=True, socket_connect_timeout=5)
                await self.redis.ping()
                logger.info(f"Connected to Redis at {fallback}. Instance ID: {self.instance_id}")
                return
            raise

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

    async def is_primary_state_stale(self):
        """True if current_game_state is missing or not updated recently (primary likely stopped)."""
        try:
            raw = await self.redis.get(GAME_STATE_KEY)
            if not raw:
                return True
            data = json.loads(raw)
            ts = data.get("timestamp")
            if not ts or not isinstance(ts, str):
                return True
            try:
                # Parse ISO format (e.g. 2025-03-12T10:00:00.123456+00:00 or ...Z)
                ts_clean = ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_clean)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - dt).total_seconds()
                return age > STALE_THRESHOLD_SEC
            except Exception:
                return True
        except Exception as e:
            logger.debug(f"Stale check failed: {e}")
            return True

    async def start_new_round(self):
        """Start a new game round. Uses GameSettings for round length and phase times."""
        self.settings = get_round_settings(previous=self.settings)
        round_end = self.settings["round_end_time"]
        self.round_id = f"R{int(time.time())}"
        self.timer = round_end  # count-down from round_end to 0
        self.status = "BETTING"
        self.dice_result = None
        self.dice_values = None
        self._sent_dice_roll = False
        self._sent_dice_result = False
        self._sent_game_end = False
        self._sent_game_start = False
        logger.info(f"New Round Started: {self.round_id} (round_end={round_end}s, betting_close={self.settings['betting_close_time']}s, dice_result={self.settings['dice_result_time']}s)")

        # Persist the round start event so DB-backed APIs (frequency, recent results, etc.) keep updating.
        # This is consumed by `manage.py process_bet_queue` (event_worker_group).
        try:
            durations = {
                "betting_close_time": int(self.settings.get("betting_close_time", DEFAULT_BETTING_CLOSE_TIME)),
                "dice_roll_time": int(self.settings.get("dice_roll_time", DEFAULT_DICE_ROLL_TIME)),
                "dice_result_time": int(self.settings.get("dice_result_time", DEFAULT_DICE_RESULT_TIME)),
                "round_end_time": int(self.settings.get("round_end_time", DEFAULT_ROUND_END_TIME)),
            }
            await self.redis.xadd(
                ROUND_EVENTS_STREAM,
                {
                    "type": "round_start",
                    "round_id": self.round_id,
                    "start_time": datetime.now(timezone.utc).isoformat(),
                    "durations": json.dumps(durations),
                },
                maxlen=50000,
                approximate=True,
            )
        except Exception as e:
            logger.warning(f"Failed to publish round_start to {ROUND_EVENTS_STREAM}: {e}")

    async def publish_ws_event(self, event_type: str, timer_count_up: int):
        """
        Publish a one-off WS event (JSON) to the WS channel.
        Consumers forward this directly to clients.
        """
        if not self.redis:
            return
        try:
            round_end = int(self.settings.get("round_end_time", DEFAULT_ROUND_END_TIME))
            betting_close = int(self.settings.get("betting_close_time", DEFAULT_BETTING_CLOSE_TIME))
            dice_roll_time = int(self.settings.get("dice_roll_time", DEFAULT_DICE_ROLL_TIME))
            dice_result_time = int(self.settings.get("dice_result_time", DEFAULT_DICE_RESULT_TIME))
        except Exception:
            round_end = DEFAULT_ROUND_END_TIME
            betting_close = DEFAULT_BETTING_CLOSE_TIME
            dice_roll_time = DEFAULT_DICE_ROLL_TIME
            dice_result_time = DEFAULT_DICE_RESULT_TIME

        payload = {
            "type": event_type,
            "round_id": self.round_id,
            "timer": int(timer_count_up),
            "status": (self.status or "").lower(),
            "server_time": int(time.time()),
            # Keep parity with /api/game/settings/
            "round_end_time": round_end,
            "betting_close_time": betting_close,
            "dice_roll_time": dice_roll_time,
            "dice_result_time": dice_result_time,
            "BETTING_CLOSE_TIME": betting_close,
            "DICE_ROLL_TIME": dice_roll_time,
            "DICE_RESULT_TIME": dice_result_time,
            "ROUND_END_TIME": round_end,
        }

        # Only include dice fields once they exist
        if self.dice_values is not None:
            payload["dice_values"] = self.dice_values
        if self.dice_result is not None:
            payload["dice_result"] = self.dice_result

        # Keep last round results API fresh even if DB settlement lags.
        # Update cache when result is known, or at game end.
        if event_type in ("dice_result", "game_end") and self.dice_values is not None:
            try:
                dv = list(self.dice_values) if isinstance(self.dice_values, (list, tuple)) else []
                if len(dv) == 6:
                    last_payload = {
                        "round_id": self.round_id,
                        "dice_1": int(dv[0]),
                        "dice_2": int(dv[1]),
                        "dice_3": int(dv[2]),
                        "dice_4": int(dv[3]),
                        "dice_5": int(dv[4]),
                        "dice_6": int(dv[5]),
                        "dice_result": self.dice_result,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    await self.redis.set("last_round_results_cache", json.dumps(last_payload), ex=120)
            except Exception:
                pass

        await self.redis.publish(GAME_ROOM_CHANNEL, json.dumps(payload))

    async def publish_state(self, publish_channels: bool = True):
        """Publish game state to Redis (both JSON and MessagePack).
        Timer is count-UP 1..round_end_time to match frontend and GameSettings (when to close bets, result, round end).
        """
        round_end = self.settings["round_end_time"]
        dice_roll_time = self.settings.get("dice_roll_time") or DEFAULT_DICE_ROLL_TIME
        # Engine counts down round_end→0; UI expects count-up 1→round_end
        timer_count_up = (round_end - self.timer) + 1 if self.timer > 0 else round_end
        timer_count_up = max(1, min(round_end, timer_count_up))

        # Derived helpers (keep in payload so clients can always align with server timing)
        try:
            betting_close = int(self.settings.get("betting_close_time", DEFAULT_BETTING_CLOSE_TIME))
            dice_result_time = int(self.settings.get("dice_result_time", DEFAULT_DICE_RESULT_TIME))
            dice_roll_time = int(dice_roll_time)
        except Exception:
            betting_close = DEFAULT_BETTING_CLOSE_TIME
            dice_result_time = DEFAULT_DICE_RESULT_TIME
            dice_roll_time = DEFAULT_DICE_ROLL_TIME

        is_rolling = bool(dice_roll_time <= timer_count_up < dice_result_time)
        betting_open = bool(timer_count_up <= betting_close)

        state = {
            "type": "timer",
            "round_id": self.round_id,
            "timer": timer_count_up,
            "status": self.status.lower(),
            "dice_result": self.dice_result,
            "dice_values": self.dice_values,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "server_time": int(time.time()),
            # Game settings (same as /api/game/settings/) so WebSocket follows API
            "round_end_time": round_end,
            "betting_close_time": betting_close,
            "dice_roll_time": dice_roll_time,
            "dice_result_time": dice_result_time,
            # Convenience flags for clients (avoid off-by-one / timer direction bugs)
            "betting_open": betting_open,
            "is_rolling": is_rolling,
            # Also include API-style keys for direct parity checks
            "BETTING_CLOSE_TIME": betting_close,
            "DICE_ROLL_TIME": dice_roll_time,
            "DICE_RESULT_TIME": dice_result_time,
            "ROUND_END_TIME": round_end,
        }
        
        try:
            # JSON for compatibility
            state_json = json.dumps(state)
            # Keep Redis hot-keys updated for betting APIs (single pipeline round-trip)
            # NOTE: These keys are relied upon by REST `POST /api/game/bet/` and WS `place_bet`.
            now_ts = int(time.time())
            # Round end epoch (updated each tick; consumers use it as a safety guard)
            end_time_epoch = now_ts + max(0, int(round_end) - int(timer_count_up))

            pipe = self.redis.pipeline()
            pipe.set(GAME_STATE_KEY, state_json, ex=120)
            pipe.set(CURRENT_ROUND_ID_KEY, str(self.round_id or ""), ex=120)
            pipe.set(CURRENT_STATUS_KEY, str(self.status or "WAITING").upper(), ex=120)
            pipe.set(CURRENT_END_TIME_KEY, str(end_time_epoch), ex=120)
            await pipe.execute()

            if publish_channels:
                await self.redis.publish(GAME_UPDATE_CHANNEL, state_json)
                # WebSocket consumer (consumers.py) subscribes to "game_room" — must publish here for timer in UI
                await self.redis.publish(GAME_ROOM_CHANNEL, state_json)
            
            # MessagePack for performance (binary)
            try:
                import msgpack
                state_msgpack = msgpack.packb(state)
                await self.redis.set(f"{GAME_STATE_KEY}_msgpack", state_msgpack, ex=120)
                if publish_channels:
                    await self.redis.publish(f"{GAME_UPDATE_CHANNEL}_msgpack", state_msgpack)
            except ImportError:
                logger.warning("msgpack not installed, skipping binary format")
            
            # Also update round_timer for compatibility (rest of app expects count-up 1..round_end)
            await self.redis.set("round_timer", str(timer_count_up), ex=120)
            
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
        """The actual game logic. Uses GameSettings: when to close bets, when to show result, round end."""
        logger.info("Starting game loop as LEADER")
        
        while self.is_leader:
            try:
                await self.start_new_round()
                betting_close = self.settings["betting_close_time"]
                dice_roll_time = int(self.settings.get("dice_roll_time", DEFAULT_DICE_ROLL_TIME))
                dice_result_time = self.settings["dice_result_time"]
                round_end = self.settings["round_end_time"]
                
                while self.timer > 0 and self.is_leader:
                    # Count-up value (1..round_end) for phase logic
                    timer_count_up = (round_end - self.timer) + 1 if self.timer > 0 else round_end
                    timer_count_up = max(1, min(round_end, timer_count_up))

                    # Emit game start event on the first second of the round.
                    if (not self._sent_game_start) and timer_count_up == 1:
                        self._sent_game_start = True
                        await self.publish_ws_event("game_start", timer_count_up)

                    # Emit dice roll warning event at exact DICE_ROLL_TIME
                    if (not self._sent_dice_roll) and timer_count_up == dice_roll_time and dice_roll_time < dice_result_time:
                        self._sent_dice_roll = True
                        await self.publish_ws_event("dice_roll", timer_count_up)
                    
                    # Status from GameSettings: same as start_game_timer and frontend
                    if timer_count_up <= betting_close:
                        self.status = "BETTING"
                    elif timer_count_up < dice_result_time:
                        self.status = "CLOSED"
                    else:
                        if self.status != "RESULT":
                            self.status = "RESULT"
                            # Admin dice control: if a manual dice result was pre-set, use it.
                            # This is written by `admin_views.set_individual_dice_view` / `set_dice_result_view`
                            # as a comma-separated string like "1,2,3,4,5,6" or "1,1,1,1,1,1".
                            manual_dice = None
                            try:
                                raw = await self.redis.get("manual_dice_result")
                                if raw:
                                    parts = [p.strip() for p in str(raw).split(",")]
                                    vals = [int(p) for p in parts if p != ""]
                                    if len(vals) == 6 and all(1 <= v <= 6 for v in vals):
                                        manual_dice = vals
                            except Exception:
                                manual_dice = None

                            if manual_dice is not None:
                                self.dice_values = manual_dice
                                try:
                                    from game.utils import determine_winning_number
                                    self.dice_result = determine_winning_number(self.dice_values)
                                except Exception:
                                    self.dice_result = "0"
                                try:
                                    await self.redis.delete("manual_dice_result")
                                except Exception:
                                    pass
                            else:
                                self.dice_values, self.dice_result = await generate_smart_dice_result(
                                    self.redis, self.round_id
                                )
                            await self.push_settlement(self.dice_values, self.dice_result)
                            logger.info(f"Dice rolled: {self.dice_values} -> Result: {self.dice_result}")
                            # Emit dice result event exactly at DICE_RESULT_TIME (once per round)
                            if not self._sent_dice_result:
                                self._sent_dice_result = True
                                await self.publish_ws_event("dice_result", timer_count_up)

                            # Persist round result for DB-backed APIs.
                            try:
                                await self.redis.xadd(
                                    ROUND_EVENTS_STREAM,
                                    {
                                        "type": "round_result",
                                        "round_id": self.round_id,
                                        "dice_values": json.dumps(self.dice_values or []),
                                        "result": str(self.dice_result or ""),
                                        "end_time": datetime.now(timezone.utc).isoformat(),
                                    },
                                    maxlen=50000,
                                    approximate=True,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to publish round_result to {ROUND_EVENTS_STREAM}: {e}")
                    
                    await self.publish_state()
                    
                    for _ in range(10):
                        await asyncio.sleep(0.1)
                        if not self.is_leader:
                            logger.warning("Lost leadership during game loop")
                            break
                    
                    self.timer -= 1
                
                if self.is_leader:
                    self.status = "COMPLETED"
                    # Avoid publishing a second "timer=ROUND_END" tick at end-of-round.
                    # Instead, send a single explicit game_end event at ROUND_END_TIME.
                    if not self._sent_game_end:
                        self._sent_game_end = True
                        await self.publish_ws_event("game_end", round_end)
                    # Still update Redis keys so REST consumers see COMPLETED, but don't re-publish on WS.
                    await self.publish_state(publish_channels=False)
                    logger.info(f"Round {self.round_id} completed")
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in game loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def run(self):
        """Main run loop with leader election. Standby instances only take over when primary state is stale."""
        await self.connect_redis()
        
        if STANDBY_MODE:
            logger.info("Game Engine started in STANDBY mode (will take over only when primary on 74 stops).")
        else:
            logger.info("Game Engine started as PRIMARY candidate, waiting for leadership...")
        
        while True:
            try:
                if not self.is_leader:
                    # Standby: only try to become leader when primary's state is stale
                    if STANDBY_MODE and not await self.is_primary_state_stale():
                        await asyncio.sleep(2)
                        continue
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
    # Required so game_engine can load GameSettings (betting close, dice result, round end)
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dice_game.settings")
    import django
    django.setup()

    engine = GameEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Engine stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
