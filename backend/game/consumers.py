import json
import asyncio
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.conf import settings
import redis
from .models import GameRound, Bet

logger = logging.getLogger('game.websocket')
from .utils import (
    generate_random_dice_values,
    apply_dice_values_to_round,
    extract_dice_values,
    sync_database_to_redis,
    sync_round_to_redis,
    get_game_setting,
    calculate_current_timer,
)

# Redis connection using connection pool (optimized for scalability)
try:
    if hasattr(settings, 'REDIS_POOL') and settings.REDIS_POOL:
        redis_client = redis.Redis(connection_pool=settings.REDIS_POOL)
        redis_client.ping()  # Test connection
    else:
        # Fallback to direct connection if pool not available
        redis_kwargs = {
            'host': settings.REDIS_HOST,
            'port': settings.REDIS_PORT,
            'db': settings.REDIS_DB,
            'decode_responses': True
        }
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
        redis_client = redis.Redis(**redis_kwargs)
        redis_client.ping()
except (redis.ConnectionError, redis.TimeoutError, AttributeError):
    redis_client = None  # Use None if Redis unavailable


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # NEVER close connection on errors - keep it alive
        try:
            await self.accept()
            self.room_group_name = 'game_room'
            self.admin_notifications_group = 'admin_notifications'
            
            user = self.scope.get('user')
            logger.info(f"WebSocket attempt from user: {user} (is_staff: {getattr(user, 'is_staff', False)})")
            
            # Ensure channel_layer is available
            if not hasattr(self, 'channel_layer') or self.channel_layer is None:
                from channels.layers import get_channel_layer
                self.channel_layer = get_channel_layer()
            
            # Join game room group
            try:
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"User {user} joined room group: {self.room_group_name}")
            except Exception as group_error:
                logger.warning(f"Failed to join game group: {group_error}")
            
            # If user is staff, join admin notifications group
            if user and hasattr(user, 'is_staff') and user.is_staff:
                try:
                    await self.channel_layer.group_add(
                        self.admin_notifications_group,
                        self.channel_name
                    )
                    logger.info(f"✅ Admin {user.username} joined notifications group: {self.channel_name}")
                except Exception as admin_group_error:
                    logger.warning(f"Failed to join admin group: {admin_group_error}")
            else:
                logger.debug(f"User {user} is NOT staff, skipping admin notifications group")
            
            logger.info(f"WebSocket connected successfully: {self.channel_name}")
            
            # Send current state
            try:
                await self.send_current_state()
                # Also send a small timer update to "kickstart" the client UI
                # this helps if the client only listens to 'timer' for updates
                # but 'game_state' for initial setup
                round_obj = await self.get_current_round_from_db()
                if round_obj:
                    # calculate_current_timer performs DB queries for settings, must be sync_to_async
                    from channels.db import database_sync_to_async
                    timer = await database_sync_to_async(calculate_current_timer)(round_obj.start_time)
                    await self.send(text_data=json.dumps({
                        'type': 'timer',
                        'timer': timer,
                        'status': round_obj.status,
                        'round_id': round_obj.round_id,
                        'is_rolling': (await database_sync_to_async(get_game_setting)('DICE_ROLL_TIME', 19) <= timer < await database_sync_to_async(get_game_setting)('DICE_RESULT_TIME', 51))
                    }))
            except Exception as state_error:
                logger.error(f"Failed to send initial state: {state_error}")
        except Exception as e:
            logger.exception(f"WebSocket connect error: {e}")

    async def disconnect(self, close_code):
        # Leave room groups
        user = self.scope.get('user')
        logger.info(f"WebSocket disconnected for user {user}: {self.channel_name} (Code: {close_code})")
        try:
            if hasattr(self, 'room_group_name'):
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            if hasattr(self, 'admin_notifications_group'):
                await self.channel_layer.group_discard(
                    self.admin_notifications_group,
                    self.channel_name
                )
        except Exception as e:
            logger.exception(f"WebSocket disconnect error: {e}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages - NEVER closes connection on error"""
        user = self.scope.get('user')
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            logger.debug(f"WebSocket message received from {user}: {message_type}")

            if message_type == 'get_state':
                await self.send_current_state()
            elif message_type == 'ping':
                # Respond to ping with pong to keep connection alive
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON received from {user}: {e}, but keeping connection alive")
        except Exception as e:
            logger.warning(f"Error handling received message from {user}: {e}")

    async def send_current_state(self):
        """Send current game state to client - NEVER closes connection on error"""
        try:
            # Try Redis first, fallback to database
            round_data = None
            timer = 0
            
            if redis_client:
                try:
                    # Use Redis pipeline for efficient batch reads (reduces round trips)
                    pipe = redis_client.pipeline()
                    pipe.get('current_round')
                    pipe.get('round_timer')
                    results = pipe.execute()
                    
                    round_data = results[0]
                    timer_raw = int(results[1] or '1')
                    # Get round_end_time from settings - always fresh from database
                    from .utils import get_game_setting
                    round_end_time = await database_sync_to_async(get_game_setting)('ROUND_END_TIME', 80)
                    # Convert 0-(round_end_time-1) to 1-round_end_time format
                    timer = round_end_time if timer_raw == 0 else timer_raw
                    
                    if not round_data:
                        # Redis key expired or missing - force sync from DB
                        await self.sync_db_to_redis()
                        # Allow fallback to DB logic below by keeping round_data=None
                        pass
                except Exception as e:
                    logger.warning(f"Redis read error (using fallback): {e}")
                    round_data = None
        
            # Fallback to database if Redis unavailable
            if not round_data:
                try:
                    round_obj = await self.get_current_round_from_db()
                    if round_obj:
                        from .utils import get_game_setting
                        round_end_time = await database_sync_to_async(get_game_setting)('ROUND_END_TIME', 80)
                        elapsed = (timezone.now() - round_obj.start_time).total_seconds()
                        # If round is older than round_end_time seconds, it should be completed
                        if elapsed >= round_end_time:
                            timer = 1  # Start new round at 1
                            status = 'WAITING'
                        else:
                            # Calculate timer using helper (1 to round_end_time)
                            timer = calculate_current_timer(round_obj.start_time, round_end_time)
                            status = round_obj.status
                        # Try to sync to Redis if available
                        if redis_client:
                            try:
                                await self.sync_round_to_redis_async(round_obj)
                            except Exception:
                                pass  # Non-critical
                        await self.send(text_data=json.dumps({
                            'type': 'game_state',
                            'round_id': round_obj.round_id,
                            'status': status,
                            'timer': timer,
                            'is_rolling': (await database_sync_to_async(get_game_setting)('DICE_ROLL_TIME', 19) <= timer < await database_sync_to_async(get_game_setting)('DICE_RESULT_TIME', 51))
                        }))
                        return
                    else:
                        # No active round - check if we need to create one
                        latest_round = await self.get_latest_round_from_db()
                        if latest_round and latest_round.status == 'COMPLETED':
                            # All rounds completed, game timer should create a new one
                            await self.send(text_data=json.dumps({
                                'type': 'game_state',
                                'status': 'WAITING',
                                'timer': 1,
                            }))
                            return
                except Exception as db_error:
                    logger.warning(f"Database error getting round (sending default state): {db_error}")
            
            if round_data:
                try:
                    round_data = json.loads(round_data)
                    # Ensure timer is in 1-round_end_time format (convert 0 to round_end_time)
                    from .utils import get_game_setting
                    round_end_time = await database_sync_to_async(get_game_setting)('ROUND_END_TIME', 80)
                    if timer == 0:
                        timer = round_end_time
                    await self.send(text_data=json.dumps({
                        'type': 'game_state',
                        'round_id': round_data.get('round_id'),
                        'status': round_data.get('status'),
                        'timer': timer,
                        'is_rolling': (await database_sync_to_async(get_game_setting)('DICE_ROLL_TIME', 19) <= timer < await database_sync_to_async(get_game_setting)('DICE_RESULT_TIME', 51))
                    }))
                except Exception as parse_error:
                    logger.warning(f"Error parsing round_data, sending default state: {parse_error}")
                    await self.send(text_data=json.dumps({
                        'type': 'game_state',
                        'status': 'WAITING',
                        'timer': 1,
                    }))
            else:
                await self.send(text_data=json.dumps({
                    'type': 'game_state',
                    'status': 'WAITING',
                    'timer': 1,
                }))
        except Exception as e:
            # CRITICAL: Never let errors in send_current_state close the connection
            logger.error(f"Error in send_current_state (connection remains open): {e}", exc_info=True)
            # Send minimal state to keep connection alive
            try:
                await self.send(text_data=json.dumps({
                    'type': 'game_state',
                    'status': 'WAITING',
                    'timer': 1,
                }))
            except Exception:
                pass  # If we can't even send this, connection might be truly dead
    
    @database_sync_to_async
    def get_current_round_from_db(self):
        """Get current round from database"""
        try:
            return GameRound.objects.filter(status__in=['BETTING', 'CLOSED', 'RESULT']).order_by('-start_time').first()
        except:
            return None
    
    @database_sync_to_async
    def get_latest_round_from_db(self):
        """Get latest round from database (any status)"""
        try:
            return GameRound.objects.order_by('-start_time').first()
        except:
            return None
    
    @database_sync_to_async
    def sync_db_to_redis(self):
        """Sync database to Redis"""
        if redis_client:
            from .utils import sync_database_to_redis
            return sync_database_to_redis(redis_client)
        return False
    
    @database_sync_to_async
    def sync_round_to_redis_async(self, round_obj):
        """Sync a round object to Redis"""
        if redis_client:
            from .utils import sync_round_to_redis
            return sync_round_to_redis(round_obj, redis_client)
        return False

    async def game_start(self, event):
        """Send game start message to WebSocket - NEVER closes connection on error"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'game_start',
                'timer': event.get('timer', 1),
                'status': event.get('status', 'BETTING'),
                'round_id': event.get('round_id'),
                'is_rolling': event.get('is_rolling', False),
            }))
        except Exception as e:
            logger.warning(f"Error sending game_start message (connection remains open): {e}")
    
    async def timer(self, event):
        """Send timer update to WebSocket - NEVER closes connection on error"""
        try:
            message = {
                'type': 'timer',
                'timer': event.get('timer', 0),
                'status': event.get('status', 'BETTING'),
                'round_id': event.get('round_id'),
                'is_rolling': event.get('is_rolling', False),
            }
            
            # Timer messages should NOT include dice values
            # Dice values are sent ONLY via dedicated dice_result message type at dice_result_time
            # This prevents dice values from appearing in every timer message
            
            await self.send(text_data=json.dumps(message))
            # Log every 10 seconds to avoid spam
            if message.get('timer', 0) % 10 == 0:
                logger.info(f"📤 Sent timer message: {message}")
        except Exception as e:
            # Log error but NEVER close connection - just skip this message
            logger.warning(f"Error sending timer message (connection remains open): {e}")
    
    async def game_timer(self, event):
        """Legacy handler - redirects to timer"""
        await self.timer(event)

    async def dice_result(self, event):
        """Send dice result to WebSocket - sent ONLY once at dice_result_time - NEVER closes connection on error"""
        try:
            timer = event.get('timer')
            # Ensure timer is not 0 - use dice_result_time if timer is missing or 0
            if not timer or timer == 0:
                from .utils import get_game_setting
                timer = await database_sync_to_async(get_game_setting)('DICE_RESULT_TIME', 51)
            
            message = {
                'type': 'dice_result',
                'timer': timer,
                'status': event.get('status', 'RESULT'),
                'round_id': event.get('round_id'),
                'is_rolling': False,
            }
            
            # Include dice_values if provided as array
            if 'dice_values' in event:
                message['dice_values'] = event['dice_values']
            
            # Include individual dice values if provided
            for i in range(1, 7):
                dice_key = f'dice_{i}'
                if dice_key in event:
                    message[dice_key] = event[dice_key]
            
            # Include dice_result (winning number) if provided
            if 'result' in event:
                message['result'] = event['result']
            
            await self.send(text_data=json.dumps(message))
        except Exception as e:
            logger.warning(f"Error sending dice_result message (connection remains open): {e}")

    async def result(self, event):
        """Send result message to WebSocket - NEVER closes connection on error"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'result',
                'timer': event.get('timer', 0),
                'status': event.get('status', 'RESULT'),
                'round_id': event.get('round_id'),
                'dice_values': event.get('dice_values'),
            }))
        except Exception as e:
            logger.warning(f"Error sending result message (connection remains open): {e}")
    
    async def game_end(self, event):
        """Send game end message to WebSocket - triggered when round ends - NEVER closes connection on error"""
        try:
            message = {
                'type': 'game_end',
                'timer': event.get('timer', 0),
                'status': event.get('status', 'COMPLETED'),
                'round_id': event.get('round_id'),
            }
            
            # Include time and date information
            if 'end_time' in event:
                message['end_time'] = event['end_time']
            if 'start_time' in event:
                message['start_time'] = event['start_time']
            if 'result_time' in event:
                message['result_time'] = event['result_time']
            
            # Include dice values if available
            if 'dice_values' in event:
                message['dice_values'] = event['dice_values']
            
            # Include individual dice values if available
            for i in range(1, 7):
                dice_key = f'dice_{i}'
                if dice_key in event:
                    message[dice_key] = event[dice_key]
            
            # Include dice_result (winning number) if available
            if 'result' in event:
                message['result'] = event['result']
            
            await self.send(text_data=json.dumps(message))
            logger.info(f"📤 Sent game_end message: round_id={message.get('round_id')}, timer={message.get('timer')}")
        except Exception as e:
            logger.warning(f"Error sending game_end message (connection remains open): {e}")

    async def dice_roll(self, event):
        """Handle dice roll warning event - sent at configured dice_roll_time from dashboard - NEVER closes connection on error"""
        try:
            message = {
                'type': 'dice_roll',
                'timer': event.get('timer', 0),
                'status': event.get('status', 'CLOSED'),
                'round_id': event.get('round_id'),
                'dice_roll_time': event.get('dice_roll_time'),  # Seconds before dice result when warning is sent
                'is_rolling': True,
            }
            # Ensure status is not None
            if message['status'] is None:
                message['status'] = 'CLOSED'
            await self.send(text_data=json.dumps(message))
        except Exception as e:
            logger.warning(f"Error sending dice_roll message (connection remains open): {e}")

    async def round_update(self, event):
        """Send round update to WebSocket - NEVER closes connection on error"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'round_update',
                'round_id': event['round_id'],
                'status': event['status'],
            }))
        except Exception as e:
            logger.warning(f"Error sending round_update message (connection remains open): {e}")

    async def game_state(self, event):
        """Send game state to WebSocket - NEVER closes connection on error"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'game_state',
                'round_id': event.get('round_id'),
                'status': event.get('status'),
                'timer': event.get('timer'),
            }))
        except Exception as e:
            logger.warning(f"Error sending game_state message (connection remains open): {e}")

    async def admin_notification(self, event):
        """Send admin notification to WebSocket"""
        try:
            # Send the entire event data to the client
            # This ensures all fields like id, user_id, screenshot_url, etc. are included
            await self.send(text_data=json.dumps(event))
        except Exception as e:
            logger.warning(f"Error sending admin_notification: {e}")

# REMOVED: Orphaned async game_timer_task() function (was ~400 lines)
# This was NEVER called and would conflict with the management command (start_game_timer.py)
# The actual game timer runs via: python manage.py start_game_timer
# DO NOT RESTORE - This would cause duplicate timer loops, race conditions, and message conflicts!


@database_sync_to_async
def update_round_status(round_id, status):
    """Update round status in database"""
    try:
        round_obj = GameRound.objects.get(round_id=round_id)
        round_obj.status = status
        if status == 'CLOSED':
            round_obj.betting_close_time = timezone.now()
        round_obj.save()
    except GameRound.DoesNotExist:
        pass


def extract_dice_values_stub(round_data, fallback=None):
    """Extract dice values from the cached round data for async contexts."""
    values = []
    for index in range(1, 7):
        value = round_data.get(f'dice_{index}')
        if value is None:
            value = fallback
        values.append(value)
    return values


@database_sync_to_async
def get_or_set_random_result(round_id):
    """Get or set random dice result and provide dice values."""
    try:
        round_obj = GameRound.objects.get(round_id=round_id)
        dice_values = None
        
        # Check if dice values are actually set (dice_1 through dice_6)
        dice_values_missing = any(
            getattr(round_obj, f'dice_{i}', None) is None 
            for i in range(1, 7)
        )
        
        # Auto-roll if dice_result is missing OR if any individual dice values are missing
        if not round_obj.dice_result or dice_values_missing:
            dice_values, result = generate_random_dice_values()
            apply_dice_values_to_round(round_obj, dice_values)
            round_obj.dice_result = result
            round_obj.status = 'RESULT'
            round_obj.result_time = timezone.now()
            round_obj.save()
            
            # Create dice result record
            from .models import DiceResult
            DiceResult.objects.update_or_create(
                round=round_obj,
                defaults={'result': result}
            )
            
            # Calculate payouts
            from .views import calculate_payouts
            calculate_payouts(round_obj, dice_result=result, dice_values=dice_values)
            return result, dice_values
        
        return round_obj.dice_result, extract_dice_values(
            round_obj, fallback=round_obj.dice_result
        )
    except GameRound.DoesNotExist:
        return None, None


@database_sync_to_async
def start_new_round():
    """Start a new game round"""
    from .models import GameRound
    from .utils import get_game_setting
    round_obj = GameRound.objects.create(
        round_id=f"R{int(timezone.now().timestamp())}",
        status='BETTING',
        betting_close_seconds=get_game_setting('BETTING_CLOSE_TIME', 30),
        dice_roll_seconds=get_game_setting('DICE_ROLL_TIME', 7),
        dice_result_seconds=get_game_setting('DICE_RESULT_TIME', 51),
        round_end_seconds=get_game_setting('ROUND_END_TIME', 80)
    )
    
    round_data = {
        'round_id': round_obj.round_id,
        'status': 'BETTING',
        'start_time': round_obj.start_time.isoformat(),
        'timer': 0,
    }
    redis_client.set('current_round', json.dumps(round_data), ex=60)
    redis_client.set('round_timer', '0', ex=60)

