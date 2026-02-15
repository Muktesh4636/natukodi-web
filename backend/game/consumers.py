import json
import asyncio
import logging
import time
import redis.asyncio as redis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

logger = logging.getLogger('game.websocket')

# Configuration
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

# Global Redis client (shared pool)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

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
            
            # 2. Join Channels groups (Only for admin notifications now)
            user = self.scope.get('user')
            if user and getattr(user, 'is_staff', False):
                await self.channel_layer.group_add('admin_notifications', self.channel_name)

            # 3. Start Redis listener in background
            self.redis_task = asyncio.create_task(self.redis_listener())
            
            # 4. Start Heartbeat to keep connection alive
            self.heartbeat_task = asyncio.create_task(self.heartbeat())
            
            # 5. Give listener a moment to subscribe before sending initial state
            await asyncio.sleep(0.5)
            
            # 6. Send initial state
            await self.send_initial_state()
            
            logger.info(f"WebSocket connected: {self.channel_name}")
        except Exception as e:
            logger.error(f"Connect error: {e}")
            await self.close()

    async def heartbeat(self):
        """Send a ping every 20 seconds to keep connection alive through load balancers"""
        while self._is_connected:
            try:
                await asyncio.sleep(20)
                if self._is_connected:
                    await self.send(text_data=json.dumps({"type": "heartbeat", "server_time": int(time.time())}))
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
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            user = self.scope.get('user')
            if user and getattr(user, 'is_staff', False):
                await self.channel_layer.group_discard('admin_notifications', self.channel_name)
        except:
            pass
            
        logger.info(f"WebSocket disconnected: {self.channel_name} (code: {close_code})")

    async def send_initial_state(self):
        """Send game_state message on connect with current round info"""
        try:
            state_raw = await redis_client.get('current_game_state')
            if state_raw:
                try:
                    state = json.loads(state_raw)
                    server_time = state.get('server_time', 0)
                    now = int(time.time())
                    age = now - server_time
                    
                    # Only send if state is fresh (less than 10 seconds old)
                    if age <= 10:
                        game_state_message = {
                            "type": "game_state",
                            "round_id": state.get('round_id', ''),
                            "status": state.get('status', 'BETTING'),
                            "timer": state.get('timer', 1)
                        }
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
                # Create a fresh Redis connection for this listener
                listener_redis = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
                pubsub = listener_redis.pubsub()
                await pubsub.subscribe(self.room_group_name)
                
                # Wait for subscription confirmation - try multiple times
                subscribe_confirmed = False
                for attempt in range(3):
                    subscribe_msg = await pubsub.get_message(timeout=1.0)
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
                    logger.warning(f"Subscription confirmation failed after 3 attempts for {self.channel_name}")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    continue
                
                # Use get_message with timeout instead of async for to allow periodic checks
                loop_iterations = 0
                logger.info(f"Starting message loop for {self.channel_name}")
                while self._is_connected:
                    loop_iterations += 1
                    try:
                        # Get message with 1 second timeout to allow periodic health checks
                        message = await pubsub.get_message(timeout=1.0)
                        
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
        """Handle incoming messages (ping)"""
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
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
