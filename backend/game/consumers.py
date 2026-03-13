import json
import asyncio
import logging
import time
import redis.asyncio as redis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.utils import timezone
from .utils import get_game_setting

logger = logging.getLogger('game.websocket')

# Configuration
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

# Global Redis client (shared pool)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Redis set of user_ids currently watching the game (WebSocket connected)
GAME_WATCHING_USERS_KEY = "game_watching_users"

PLACE_BET_AND_QUEUE_LUA = r"""
-- Redis-First Bet Placement + Queueing (Atomic)
-- Keys:
--  1 user_balance_key
--  2 round_total_exposure_key
--  3 round_user_exposure_hash_key
--  4 round_bet_count_key
--  5 legacy_round_total_amount_key
--  6 legacy_round_total_bets_key
--  7 bet_stream_key
--  8 user_bets_stack_key
-- Args:
--  1 bet_amount
--  2 user_id
--  3 ttl_seconds
--  4 round_id
--  5 number
--  6 username
--  7 timestamp_iso

local amount = tonumber(ARGV[1])
local user_id = tostring(ARGV[2])
local ttl = tonumber(ARGV[3])
local round_id = tostring(ARGV[4])
local number = tostring(ARGV[5])
local username = tostring(ARGV[6])
local ts = tostring(ARGV[7])

-- Ensure balance exists
local bal_raw = redis.call('GET', KEYS[1])
if not bal_raw then
  return {false, "NO_BALANCE", nil, nil, nil}
end

local bal = tonumber(bal_raw)
if not bal or bal < amount then
  return {false, "INSUFFICIENT_BALANCE", tostring(bal_raw), nil, nil}
end

-- 1) Deduct balance atomically
local new_balance = tonumber(redis.call('INCRBYFLOAT', KEYS[1], -amount))
redis.call('EXPIRE', KEYS[1], 86400)

-- 2) Update exposure totals
local total_exp = tonumber(redis.call('INCRBYFLOAT', KEYS[2], amount))
redis.call('EXPIRE', KEYS[2], ttl)

local user_exp = tonumber(redis.call('HINCRBYFLOAT', KEYS[3], user_id, amount))
redis.call('EXPIRE', KEYS[3], ttl)

-- 3) Increment counters (legacy)
local bet_count = tonumber(redis.call('INCR', KEYS[4]))
redis.call('EXPIRE', KEYS[4], ttl)

local legacy_amount = tonumber(redis.call('INCRBYFLOAT', KEYS[5], amount))
redis.call('EXPIRE', KEYS[5], ttl)

local legacy_bets = tonumber(redis.call('INCR', KEYS[6]))
redis.call('EXPIRE', KEYS[6], ttl)

-- 4) Queue bet event in Redis Stream
local msg_id = redis.call(
  'XADD', KEYS[7],
  'MAXLEN', '~', 10000,
  '*',
  'type', 'place_bet',
  'user_id', user_id,
  'round_id', round_id,
  'number', number,
  'chip_amount', tostring(amount),
  'username', username,
  'timestamp', ts
)

-- 5) Push to per-user stack for "remove last bet"
redis.call('LPUSH', KEYS[8], msg_id)
redis.call('EXPIRE', KEYS[8], ttl)

return {true, tostring(new_balance), msg_id, tostring(legacy_bets), tostring(legacy_amount)}
"""

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'game_room'
        self.redis_task = None
        self.heartbeat_task = None
        self._is_connected = False

        try:
            # 1. Accept connection
            await self.accept()
            self._is_connected = True
            
            # 2. Send immediate connection acknowledgment (don't wait for Redis)
            await self.send(text_data=json.dumps({
                "type": "connected",
                "server_time": int(time.time())
            }))
            
            # 3. Track watching user for "actively playing" (authenticated users only)
            user = self.scope.get('user')
            self._watching_user_id = None
            if user and getattr(user, 'id', None):
                try:
                    await redis_client.sadd(GAME_WATCHING_USERS_KEY, str(user.id))
                    self._watching_user_id = user.id
                except Exception as e:
                    logger.debug(f"Could not add watching user: {e}")
            if user and getattr(user, 'is_staff', False):
                await self.channel_layer.group_add('admin_notifications', self.channel_name)

            # 4. Start Redis listener in background (non-blocking)
            self.redis_task = asyncio.create_task(self.redis_listener())
            
            # 5. Start Heartbeat to keep connection alive (reduced interval)
            self.heartbeat_task = asyncio.create_task(self.heartbeat())
            
            # 6. Send initial state in background (non-blocking)
            asyncio.create_task(self.send_initial_state())
            
            logger.info(f"WebSocket connected: {self.channel_name}")
        except Exception as e:
            logger.error(f"Connect error: {e}")
            await self.close()

    async def heartbeat(self):
        """Send a ping every 10 seconds to keep connection alive through load balancers"""
        # Send first heartbeat immediately, then every 10 seconds
        while self._is_connected:
            try:
                if self._is_connected:
                    await self.send(text_data=json.dumps({"type": "heartbeat", "server_time": int(time.time())}))
                await asyncio.sleep(10)  # Reduced from 20 to 10 seconds for faster feedback
            except Exception as e:
                logger.debug(f"Heartbeat send failed: {e}")
                break

    async def disconnect(self, close_code):
        self._is_connected = False
        if self.redis_task:
            self.redis_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        try:
            if getattr(self, '_watching_user_id', None) is not None:
                await redis_client.srem(GAME_WATCHING_USERS_KEY, str(self._watching_user_id))
        except Exception as e:
            logger.debug(f"Could not remove watching user: {e}")
        try:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            user = self.scope.get('user')
            if user and getattr(user, 'is_staff', False):
                await self.channel_layer.group_discard('admin_notifications', self.channel_name)
        except:
            pass
            
        logger.info(f"WebSocket disconnected: {self.channel_name} (code: {close_code})")

    async def send_initial_state(self):
        """Send game_state message on connect with current round info"""
        if not self._is_connected:
            return
            
        try:
            state_raw = await redis_client.get('current_game_state')
            if state_raw:
                try:
                    state = json.loads(state_raw)
                    now = int(time.time())
                    server_time = state.get('server_time', 0)
                    if server_time and server_time > 0:
                        age = now - server_time
                    else:
                        # Fallback: use timestamp (ISO) if server_time missing (e.g. game_engine_v3)
                        try:
                            ts = state.get('timestamp', '')
                            if ts:
                                from datetime import datetime, timezone
                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                age = (datetime.now(timezone.utc) - dt).total_seconds()
                            else:
                                age = 999
                        except Exception:
                            age = 999

                    # Only send if state is fresh (less than 15 seconds old)
                    if age <= 15:
                        game_state_message = {
                            "type": "game_state",
                            "round_id": state.get('round_id', ''),
                            "status": state.get('status', 'BETTING'),
                            "timer": state.get('timer', 1),
                            "dice_result": state.get('dice_result'),
                        }
                        # Include game settings (same as /api/game/settings/) so client matches API
                        for key in ("round_end_time", "betting_close_time", "dice_roll_time", "dice_result_time"):
                            if key in state:
                                game_state_message[key] = state[key]
                        # Also include API-style keys if present (for parity/debug on clients)
                        for key in ("BETTING_CLOSE_TIME", "DICE_ROLL_TIME", "DICE_RESULT_TIME", "ROUND_END_TIME", "betting_open", "is_rolling"):
                            if key in state:
                                game_state_message[key] = state[key]
                        if self._is_connected:
                            await self.send(text_data=json.dumps(game_state_message))
                            logger.info(f"Sent fresh initial game_state to {self.channel_name}: round={game_state_message['round_id']}, age={age}s")
                    else:
                        # State is too old, send a waiting message instead of stale data
                        waiting_message = {
                            "type": "game_state",
                            "round_id": "",
                            "status": "WAITING",
                            "timer": 0
                        }
                        if self._is_connected:
                            await self.send(text_data=json.dumps(waiting_message))
                            logger.warning(f"Initial state too old ({age}s), sent WAITING to {self.channel_name}")
                except Exception as e:
                    logger.error(f"Error parsing initial state: {e}")
            else:
                # No state in Redis, send waiting
                waiting_message = {
                    "type": "game_state",
                    "round_id": "",
                    "status": "WAITING",
                    "timer": 0
                }
                if self._is_connected:
                    await self.send(text_data=json.dumps(waiting_message))
                    logger.warning(f"No initial state in Redis, sent WAITING to {self.channel_name}")
        except Exception as e:
            logger.error(f"Initial state error: {e}")

    async def redis_listener(self):
        """Listen for Redis Pub/Sub messages continuously with reconnection"""
        message_count = 0
        reconnect_delay = 1
        max_reconnect_delay = 30
        last_message_time = time.time()
        consecutive_errors = 0
        
        while self._is_connected:
            pubsub = None
            listener_redis = None
            
            try:
                # Create a fresh Redis connection for this listener with faster timeouts
                listener_redis = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
                pubsub = listener_redis.pubsub()
                await pubsub.subscribe(self.room_group_name)
                
                # Wait for subscription confirmation - optimized with shorter timeout
                subscribe_confirmed = False
                for attempt in range(2):  # Reduced from 3 to 2 attempts
                    subscribe_msg = await pubsub.get_message(timeout=0.5)  # Reduced from 1.0 to 0.5 seconds
                    if subscribe_msg:
                        if subscribe_msg['type'] == 'subscribe':
                            logger.info(f"Redis listener subscribed to {self.room_group_name} for {self.channel_name} (attempt {attempt + 1})")
                            subscribe_confirmed = True
                            reconnect_delay = 1  # Reset delay on successful connection
                            consecutive_errors = 0
                            last_message_time = time.time()  # Reset message timer
                            break
                        elif subscribe_msg['type'] == 'message':
                            # Got a message before subscription confirmation - this is fine, process it
                            logger.info(f"Received message before subscription confirmation for {self.channel_name}")
                            subscribe_confirmed = True
                            reconnect_delay = 1
                            consecutive_errors = 0
                            last_message_time = time.time()
                            # Process this message
                            try:
                                await self.send(text_data=subscribe_msg['data'])
                                message_count += 1
                                logger.info(f"[{self.channel_name}] Processed early message #{message_count}")
                            except Exception as e:
                                logger.warning(f"Error sending early message: {e}")
                            break
                
                if not subscribe_confirmed:
                    logger.warning(f"Subscription confirmation failed after 2 attempts for {self.channel_name}")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    continue
                
                # Use get_message with timeout instead of async for to allow periodic checks
                loop_iterations = 0
                logger.info(f"Starting message loop for {self.channel_name}")
                while self._is_connected:
                    loop_iterations += 1
                    try:
                        # Get message with 0.5 second timeout for faster response
                        message = await pubsub.get_message(timeout=0.5)
                        
                        if message is None:
                            # Timeout - check if we should ping or if connection is stale
                            time_since_last_msg = time.time() - last_message_time
                            # Log every 30 iterations (30 seconds) to show listener is alive
                            if loop_iterations % 30 == 0:
                                logger.info(f"[{self.channel_name}] Listener alive: {loop_iterations} iterations, {int(time_since_last_msg)}s since last message, {message_count} total messages")
                            
                            if time_since_last_msg > 10:
                                # Try to ping Redis to verify connection is alive
                                try:
                                    await listener_redis.ping()
                                    if time_since_last_msg > 30:
                                        logger.warning(f"[{self.channel_name}] No messages for {int(time_since_last_msg)}s, but Redis ping succeeded")
                                except Exception as ping_error:
                                    logger.error(f"[{self.channel_name}] Redis ping failed after {int(time_since_last_msg)}s, reconnecting: {ping_error}")
                                    break
                            continue
                        
                        # Only process actual messages (ignore subscribe/unsubscribe confirmations)
                        if message['type'] == 'message':
                            message_count += 1
                            last_message_time = time.time()
                            consecutive_errors = 0  # Reset error count on successful message
                            
                            try:
                                await self.send(text_data=message['data'])
                                
                                # Log first 5 messages and then every 10th message for debugging
                                if message_count <= 5 or message_count % 10 == 0:
                                    try:
                                        msg_data = json.loads(message['data'])
                                        logger.info(f"[{self.channel_name}] Message #{message_count}: type={msg_data.get('type')}, round={msg_data.get('round_id')}, timer={msg_data.get('timer')}, status={msg_data.get('status')}")
                                    except:
                                        logger.info(f"[{self.channel_name}] Sent {message_count} messages")
                            except Exception as e:
                                error_str = str(e).lower()
                                consecutive_errors += 1
                                
                                # Only break on actual connection closure
                                if 'closed' in error_str or 'not connected' in error_str or isinstance(e, ConnectionError):
                                    logger.warning(f"WebSocket closed, stopping listener: {e}")
                                    self._is_connected = False
                                    break
                                else:
                                    logger.warning(f"Send error (continuing): {e} (error #{consecutive_errors})")
                                    # If too many consecutive errors, break and reconnect
                                    if consecutive_errors >= 5:
                                        logger.error(f"Too many consecutive send errors ({consecutive_errors}), reconnecting...")
                                        break
                        elif message['type'] == 'subscribe':
                            # Already handled, just continue
                            continue
                        elif message['type'] == 'unsubscribe':
                            logger.warning(f"Unexpected unsubscribe message for {self.channel_name}")
                            break
                            
                    except asyncio.TimeoutError:
                        # This is expected when get_message times out, continue loop
                        continue
                    except Exception as loop_error:
                        logger.error(f"Error in message loop for {self.channel_name}: {loop_error}")
                        consecutive_errors += 1
                        if consecutive_errors >= 5:
                            logger.error(f"Too many errors in message loop, reconnecting...")
                            break
                        await asyncio.sleep(0.1)  # Brief pause before retry
                            
            except asyncio.CancelledError:
                logger.info(f"Redis listener cancelled for {self.channel_name}")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Redis listener error for {self.channel_name}: {e} (error #{consecutive_errors})", exc_info=True)
                
                # If too many consecutive errors, give up
                if consecutive_errors >= 10:
                    logger.error(f"Too many consecutive listener errors ({consecutive_errors}), stopping listener")
                    break
            finally:
                # Clean up pubsub and redis connection
                if pubsub:
                    try:
                        await pubsub.unsubscribe(self.room_group_name)
                        await pubsub.close()
                    except Exception as e:
                        logger.debug(f"Error closing pubsub: {e}")
                
                if listener_redis:
                    try:
                        await listener_redis.aclose()
                    except Exception as e:
                        logger.debug(f"Error closing redis connection: {e}")
            
            # Reconnect with exponential backoff if still connected
            if self._is_connected:
                logger.info(f"Reconnecting Redis listener in {reconnect_delay}s... (sent {message_count} messages before reconnect)")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
        
        logger.info(f"Redis listener stopped for {self.channel_name} (sent {message_count} messages total)")

    async def receive(self, text_data):
        """Handle incoming messages (ping, place_bet)"""
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
                return

            if data.get('type') == 'place_bet':
                user = self.scope.get('user')
                if not user or not getattr(user, 'is_authenticated', False):
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'ok': False, 'error': 'Unauthorized'}))
                    return

                if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'ok': False, 'error': 'Admins are not allowed'}))
                    return

                request_id = str(data.get('request_id') or '')
                try:
                    number = int(data.get('number'))
                except Exception:
                    number = None
                try:
                    chip_amount = float(data.get('chip_amount'))
                except Exception:
                    chip_amount = None

                if number is None or chip_amount is None:
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Invalid payload'}))
                    return

                max_bet_limit = float(get_game_setting('MAX_BET', 50000))
                if chip_amount <= 0:
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Invalid bet amount'}))
                    return
                if chip_amount > max_bet_limit:
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': f'Maximum bet amount is {max_bet_limit}'}))
                    return

                user_id = user.id
                username = user.username
                balance_key = f"user_balance:{user_id}"

                # 1) Get round state and balance from Redis in one round-trip
                try:
                    pipe = redis_client.pipeline()
                    pipe.get('current_round_id')
                    pipe.get('current_status')
                    pipe.get('current_end_time')
                    pipe.get(balance_key)
                    round_id_raw, status_raw, end_time_raw, bal_raw = await pipe.execute()
                except Exception as e:
                    logger.error(f"[WS bet] Redis state fetch failed: {e}")
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Betting service unavailable'}))
                    return

                # Fallback to engine state if legacy hot keys are missing (game_engine_v3 publishes current_game_state)
                if (not round_id_raw) or (not status_raw):
                    try:
                        state_raw = await redis_client.get('current_game_state')
                        if state_raw:
                            state = json.loads(state_raw)
                            round_id_raw = state.get('round_id') or round_id_raw
                            status_raw = (state.get('status') or status_raw)
                            # Compute an end_time if missing (safety guard only)
                            if not end_time_raw:
                                try:
                                    round_end = int(state.get('ROUND_END_TIME') or state.get('round_end_time') or 0)
                                    timer = int(state.get('timer') or 0)
                                    end_time_raw = str(int(time.time()) + max(0, round_end - timer))
                                except Exception:
                                    end_time_raw = end_time_raw
                    except Exception:
                        pass

                if not round_id_raw or not status_raw:
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Game state syncing, retry'}))
                    return

                if isinstance(round_id_raw, bytes):
                    try:
                        round_id = round_id_raw.decode()
                    except Exception:
                        round_id = str(round_id_raw)
                else:
                    round_id = str(round_id_raw)

                if isinstance(status_raw, bytes):
                    try:
                        status_val = status_raw.decode()
                    except Exception:
                        status_val = str(status_raw)
                else:
                    status_val = str(status_raw)
                status_val = (status_val or "WAITING").upper()
                if status_val != 'BETTING':
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Betting is closed for this round'}))
                    return

                try:
                    end_time = int(end_time_raw or 0)
                    now_ts = int(timezone.now().timestamp())
                    if end_time > 0 and now_ts > end_time:
                        await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Betting period has expired'}))
                        return
                except Exception:
                    pass

                if bal_raw is None:
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Balance cache syncing, retry'}))
                    return

                # 2) Atomic place + queue (Lua)
                keys = [
                    balance_key,
                    f"round:{round_id}:total_exposure",
                    f"round:{round_id}:user_exposure",
                    f"round:{round_id}:bet_count",
                    f"round_total_amount:{round_id}",
                    f"round_total_bets:{round_id}",
                    "bet_stream",
                    f"user_bets_stack:{user_id}",
                ]
                ts = timezone.now().isoformat()
                try:
                    result = await redis_client.eval(
                        PLACE_BET_AND_QUEUE_LUA,
                        8,
                        *keys,
                        chip_amount,
                        user_id,
                        3600,
                        round_id,
                        number,
                        username,
                        ts,
                    )
                    success = bool(result[0])
                    response_val = result[1]
                    if not success:
                        await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': str(response_val)}))
                        return

                    new_balance = response_val
                    legacy_bets = result[3]
                    legacy_amount = result[4]

                    await self.send(text_data=json.dumps({
                        'type': 'place_bet_result',
                        'request_id': request_id,
                        'ok': True,
                        'wallet_balance': "{:.2f}".format(float(new_balance)),
                        'round': {
                            'round_id': str(round_id),
                            'total_bets': int(float(legacy_bets) if legacy_bets is not None else 0),
                            'total_amount': "{:.2f}".format(float(legacy_amount) if legacy_amount is not None else 0.0),
                        }
                    }))
                except Exception as e:
                    logger.error(f"[WS bet] Redis eval failed: {e}")
                    await self.send(text_data=json.dumps({'type': 'place_bet_result', 'request_id': request_id, 'ok': False, 'error': 'Betting service unavailable'}))
        except:
            pass

    # Handlers for channel_layer.group_send
    async def admin_notification(self, event):
        await self.send(text_data=json.dumps(event))

    async def game_state(self, event):
        await self.send(text_data=json.dumps(event))

    async def timer(self, event):
        if 'payload' in event:
            await self.send(text_data=event['payload'])
        else:
            await self.send(text_data=json.dumps(event))
