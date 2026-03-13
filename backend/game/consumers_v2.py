import json
import asyncio
import logging
import time
import msgpack
import redis.asyncio as redis
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

logger = logging.getLogger('game.websocket')

# Redis connection
REDIS_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
if settings.REDIS_PASSWORD:
    REDIS_URL = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

# Global redis client
redis_client = redis.from_url(REDIS_URL, decode_responses=False) # Binary for msgpack

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'game_room'
        self.redis_task = None
        self.heartbeat_task = None
        self.user_id = None
        self.connect_time = time.time()

        try:
            await self.accept()

            # Extract user_id from query string or scope
            try:
                from urllib.parse import parse_qs
                qs = parse_qs(self.scope.get('query_string', b'').decode())
                uid = qs.get('user_id', [None])[0]
                if uid:
                    self.user_id = int(uid)
            except Exception:
                pass

            # Start Redis listener and heartbeat
            self.redis_task = asyncio.create_task(self.redis_listener())
            if self.user_id:
                self.heartbeat_task = asyncio.create_task(self.session_heartbeat())

            # Send initial state
            await self.send_initial_state()

            logger.info(f"WebSocket connected: {self.channel_name} user={self.user_id}")
        except Exception as e:
            logger.error(f"Connect error: {e}")
            await self.close()

    async def disconnect(self, close_code):
        if self.redis_task:
            self.redis_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        logger.info(f"WebSocket disconnected: {self.channel_name} user={self.user_id}")

    async def session_heartbeat(self):
        """
        Every 60 seconds, increment the player's time_played_seconds in Redis.
        When time target is reached, mark time_target_reached = True.
        """
        str_redis = redis.from_url(REDIS_URL, decode_responses=True)
        try:
            while True:
                await asyncio.sleep(60)
                if not self.user_id:
                    continue
                try:
                    ps_key = f"player_state:{self.user_id}"
                    raw = await str_redis.get(ps_key)
                    if not raw:
                        continue
                    state = json.loads(raw)
                    played = int(state.get('time_played_seconds', 0)) + 60
                    state['time_played_seconds'] = played
                    target = int(state.get('time_target_seconds', 3600))
                    if played >= target and not state.get('time_target_reached'):
                        state['time_target_reached'] = True
                        logger.info(f"User {self.user_id} reached time target ({target}s)")
                    await str_redis.set(ps_key, json.dumps(state), ex=86400)
                except Exception as he:
                    logger.debug(f"Heartbeat error user={self.user_id}: {he}")
        except asyncio.CancelledError:
            pass
        finally:
            await str_redis.aclose()

    async def send_initial_state(self):
        try:
            # Try to get pre-serialized msgpack state first
            state_msgpack = await redis_client.get('current_game_state_msgpack')
            if state_msgpack:
                await self.send(bytes_data=state_msgpack)
            else:
                # Fallback to JSON if msgpack not ready
                state_json = await redis_client.get('current_game_state')
                if state_json:
                    data = json.loads(state_json)
                    await self.send(bytes_data=msgpack.packb(data))
        except Exception as e:
            logger.error(f"Error sending initial state: {e}")

    async def redis_listener(self):
        """Listen for direct Redis Pub/Sub messages in MessagePack format"""
        pubsub = redis_client.pubsub()
        await pubsub.subscribe('game_updates_msgpack')
        
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    # Send raw binary data directly to client
                    await self.send(bytes_data=message['data'])
        except asyncio.CancelledError:
            await pubsub.unsubscribe('game_updates_msgpack')
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
        finally:
            await pubsub.close()

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming MessagePack messages"""
        try:
            if bytes_data:
                data = msgpack.unpackb(bytes_data)
            elif text_data:
                data = json.loads(text_data)
            else:
                return

            if data.get('type') == 'ping':
                await self.send(bytes_data=msgpack.packb({'type': 'pong'}))
            
            elif data.get('type') == 'place_bet':
                # Stateless: User ID should be in the JWT scope, not trusted from client
                user = self.scope.get('user')
                if not user or not user.is_authenticated:
                    await self.send(bytes_data=msgpack.packb({'type': 'error', 'message': 'Unauthorized'}))
                    return

                bet_data = {
                    'user_id': user.id,
                    'round_id': data.get('round_id'),
                    'number': data.get('number'),
                    'chip_amount': str(data.get('amount')),
                    'timestamp': datetime.utcnow().isoformat()
                }
                # Push to Redis Stream
                await redis_client.xadd('bet_stream', bet_data)
                await self.send(bytes_data=msgpack.packb({'type': 'bet_received', 'status': 'queued'}))

        except Exception as e:
            logger.error(f"Receive error: {e}")
