import json
import logging
import time

logger = logging.getLogger('game.timer')
import redis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from game.models import GameRound, DiceResult
from game.views import calculate_payouts, get_dice_mode
from game.utils import (
    generate_random_dice_values,
    apply_dice_values_to_round,
    extract_dice_values,
    get_game_setting,
    calculate_current_timer,
)


class Command(BaseCommand):
    help = 'Start the game timer task'

    def handle(self, *args, **options):
        logger.info('Starting game timer management command')
        self.stdout.write(self.style.SUCCESS('Starting game timer...'))
        
        # Setup Redis connection with reconnection logic
        def get_or_reconnect_redis():
            """Get Redis client, reconnecting if necessary"""
            try:
                if hasattr(settings, 'REDIS_POOL') and settings.REDIS_POOL:
                    redis_client = redis.Redis(connection_pool=settings.REDIS_POOL)
                    redis_client.ping()
                    return redis_client
                else:
                    # Fallback to direct connection if pool not available
                    redis_kwargs = {
                        'host': settings.REDIS_HOST,
                        'port': settings.REDIS_PORT,
                        'db': settings.REDIS_DB,
                        'decode_responses': True,
                        'socket_connect_timeout': 5,
                        'socket_timeout': 5,
                        'retry_on_timeout': True,
                    }
                    if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
                        redis_kwargs['password'] = settings.REDIS_PASSWORD
                    redis_client = redis.Redis(**redis_kwargs)
                    redis_client.ping()
                    return redis_client
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Redis connection error: {e}'))
                return None
        
        redis_client = get_or_reconnect_redis()
        redis_host = getattr(settings, 'REDIS_HOST', 'unknown')
        redis_port = getattr(settings, 'REDIS_PORT', 'unknown')
        if redis_client:
            logger.info(f'Redis connected successfully to {redis_host}:{redis_port}')
            self.stdout.write(self.style.SUCCESS(f'✅ Redis connected to {redis_host}:{redis_port}'))
        else:
            logger.warning(f'Redis NOT available at {redis_host}:{redis_port} - using database only')
            self.stdout.write(self.style.WARNING(f'❌ Redis NOT available at {redis_host}:{redis_port} - coordination DISABLED'))
        
        # Setup channel layer
        def get_or_reconnect_channel_layer():
            """Get channel layer, reconnecting if necessary"""
            try:
                return get_channel_layer()
            except Exception as e:
                logger.error(f"Channel layer connection error: {e}")
                self.stdout.write(self.style.WARNING(f'Channel layer connection error: {e}'))
                # Try to reconnect after a short delay
                import time
                time.sleep(1)
                try:
                    return get_channel_layer()
                except Exception:
                    return None
        
        channel_layer = get_or_reconnect_channel_layer()
        if channel_layer:
            logger.info('Channel layer connected successfully for game timer')
            self.stdout.write(self.style.SUCCESS('Channel layer connected'))
        else:
            logger.warning('Channel layer not available for game timer - WebSocket broadcasts will be skipped')
            self.stdout.write(self.style.WARNING('Channel layer not available - WebSocket broadcasts will be skipped'))
        
        # Log initial settings and track for changes
        last_betting_close = get_game_setting('BETTING_CLOSE_TIME', 30)
        last_dice_rolling = get_game_setting('DICE_ROLL_TIME', 19)
        last_dice_result = get_game_setting('DICE_RESULT_TIME', 51)
        last_round_end = get_game_setting('ROUND_END_TIME', 80)
        self.stdout.write(self.style.SUCCESS(f'Initial settings loaded:'))
        self.stdout.write(self.style.SUCCESS(f'  Betting close time: {last_betting_close}s'))
        self.stdout.write(self.style.SUCCESS(f'  Dice rolling time: {last_dice_rolling}s (animation starts)'))
        self.stdout.write(self.style.SUCCESS(f'  Dice result time: {last_dice_result}s (result displayed)'))
        self.stdout.write(self.style.SUCCESS(f'  Round end time: {last_round_end}s'))
        self.stdout.write(self.style.SUCCESS('Settings will be refreshed dynamically on each iteration'))

        # Track loop timing to maintain consistent 1-second intervals
        loop_start_time = time.time()
        iteration_count = 0
        last_broadcast_timer = -1  # Track last broadcast to prevent duplicates
        
        # Cache settings to reduce DB load
        settings_cache = {}
        last_settings_fetch = 0

        while True:
            iteration_count += 1
            try:
                # Track loop iteration start time for timing calculations
                iteration_start = time.time()
                
                # Refresh settings every 10 seconds instead of every second
                if time.time() - last_settings_fetch > 10:
                    try:
                        betting_close_time = get_game_setting('BETTING_CLOSE_TIME', 30)
                        dice_rolling_time = get_game_setting('DICE_ROLL_TIME', 19)
                        dice_result_time = get_game_setting('DICE_RESULT_TIME', 51)
                        round_end_time = get_game_setting('ROUND_END_TIME', 80)
                        
                        settings_cache = {
                            'betting_close_time': betting_close_time,
                            'dice_rolling_time': dice_rolling_time,
                            'dice_result_time': dice_result_time,
                            'round_end_time': round_end_time
                        }
                        last_settings_fetch = time.time()
                        
                        # Log when settings change
                        if (betting_close_time != last_betting_close or 
                            dice_rolling_time != last_dice_rolling or 
                            dice_result_time != last_dice_result or 
                            round_end_time != last_round_end):
                            logger.info(f"Game settings updated: Betting={betting_close_time}s, Rolling={dice_rolling_time}s, Result={dice_result_time}s, End={round_end_time}s")
                            last_betting_close = betting_close_time
                            last_dice_rolling = dice_rolling_time
                            last_dice_result = dice_result_time
                            last_round_end = round_end_time
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Error fetching settings: {e}"))
                        # Use cached values if fetch fails
                        betting_close_time = settings_cache.get('betting_close_time', 30)
                        dice_rolling_time = settings_cache.get('dice_rolling_time', 19)
                        dice_result_time = settings_cache.get('dice_result_time', 51)
                        round_end_time = settings_cache.get('round_end_time', 80)
                else:
                    betting_close_time = settings_cache.get('betting_close_time', 30)
                    dice_rolling_time = settings_cache.get('dice_rolling_time', 19)
                    dice_result_time = settings_cache.get('dice_result_time', 51)
                    round_end_time = settings_cache.get('round_end_time', 80)

                # CRITICAL: Only cleanup old rounds every 30 seconds to reduce DB pressure
                now = timezone.now()
                if iteration_count % 30 == 0:
                    try:
                        old_rounds = GameRound.objects.filter(
                            status__in=['BETTING', 'CLOSED', 'RESULT']
                        ).exclude(
                            start_time__gte=now - timezone.timedelta(seconds=round_end_time + 10)
                        )
                        if old_rounds.exists():
                            count = old_rounds.count()
                            # Send game_end messages for old rounds before updating them
                            for old_round in old_rounds:
                                # Distributed lock for game_end - STRICT (requires Redis)
                                end_lock_key = f'game_end_sent_{old_round.round_id}'
                                end_lock_acquired = False
                                if redis_client:
                                    try:
                                        end_lock_acquired = redis_client.set(end_lock_key, '1', ex=300, nx=True)
                                    except Exception as e:
                                        self.stdout.write(self.style.WARNING(f'Redis connection error during game_end lock: {e}'))
                                        # Reconnect for next iteration
                                        redis_client = get_or_reconnect_redis()

                                if channel_layer and end_lock_acquired:
                                    try:
                                        async_to_sync(channel_layer.group_send)(
                                            'game_room',
                                            {
                                                'type': 'game_end',
                                                'round_id': old_round.round_id,
                                                'status': 'COMPLETED',
                                                'timer': round_end_time,
                                                'end_time': now.isoformat(),
                                                'start_time': old_round.start_time.isoformat(),
                                                'result_time': old_round.result_time.isoformat() if old_round.result_time else None,
                                            }
                                        )
                                    except Exception:
                                        pass
                            old_rounds.update(status='COMPLETED', end_time=now)
                            self.stdout.write(self.style.WARNING(f'Marked {count} old round(s) as COMPLETED'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Cleanup error (ignoring): {e}"))
                        # Close broken connections
                        from django.db import connections
                        for conn in connections.all():
                            conn.close()

                
                # Get current active round from Redis (FAST) or database (SLOW - only if Redis fails)
                round_obj = None
                if redis_client:
                    try:
                        round_data_json = redis_client.get('current_round')
                        if round_data_json:
                            round_data = json.loads(round_data_json)
                            # We still need the object to save status changes, but we can fetch it without select_for_update
                            # to avoid blocking other processes.
                            # Use timeout to prevent blocking
                            try:
                                round_obj = GameRound.objects.filter(round_id=round_data['round_id']).first()
                            except Exception as db_err:
                                self.stdout.write(self.style.WARNING(f'DB query error (non-critical): {db_err}'))
                                # Continue without round_obj - will create new one
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Redis read error: {e}'))

                # Fallback to database only if Redis didn't give us a valid round
                # CRITICAL: Add timeout handling to prevent timer from getting stuck
                if not round_obj:
                    try:
                        # Use connection timeout to prevent blocking
                        from django.db import connections
                        connections.close_all()  # Close stale connections
                        round_obj = GameRound.objects.filter(
                            status__in=['BETTING', 'CLOSED', 'RESULT']
                        ).order_by('-start_time').first()
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Database error fetching round (non-critical): {e}'))
                        # Don't sleep or continue - just proceed without round_obj
                        # Timer will create new round if needed
                        round_obj = None
                
                # Track if we just sent game_start to avoid duplicate timer message
                just_sent_game_start = False
                
                # If no active round exists, create a new one
                # Wrap in try-except to prevent blocking on DB errors
                if not round_obj:
                    try:
                        round_obj = GameRound.objects.create(
                            round_id=f"R{int(timezone.now().timestamp())}",
                            status='BETTING',
                            betting_close_seconds=betting_close_time,
                            dice_roll_seconds=dice_rolling_time,
                            dice_result_seconds=dice_result_time,
                            round_end_seconds=round_end_time
                        )
                    except Exception as db_err:
                        self.stdout.write(self.style.ERROR(f'Failed to create new round (will retry): {db_err}'))
                        # Close stale connections and continue - will retry next iteration
                        from django.db import connections
                        connections.close_all()
                        round_obj = None
                        # Continue loop - timer will keep running and retry creating round
                    # Reset flags for new round
                    round_obj._dice_roll_sent = False
                    round_obj._dice_result_sent = False
                    last_broadcast_timer = -1  # Reset for new round
                    # Clear Redis flags for previous round if any
                    if redis_client:
                        try:
                            redis_client.delete(f'dice_result_sent_{round_obj.round_id}')
                        except Exception:
                            pass
                    timer = 1  # Start at 1
                    status = 'BETTING'
                    round_data = {
                        'round_id': round_obj.round_id,
                        'status': 'BETTING',
                        'start_time': round_obj.start_time.isoformat(),
                        'timer': 1,
                    }
                    # Update Redis with new round (use pipeline for efficient batch writes)
                    if redis_client:
                        try:
                            pipe = redis_client.pipeline()
                            pipe.set('current_round', json.dumps(round_data), ex=60)
                            pipe.set('round_timer', '1', ex=60)
                            # Initialize totals in Redis for new round
                            pipe.set(f"round_total_bets:{round_obj.round_id}", "0", ex=3600)
                            pipe.set(f"round_total_amount:{round_obj.round_id}", "0.00", ex=3600)
                            pipe.execute()  # Execute all writes in one round trip
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f'Redis write error: {e}, reconnecting...'))
                            redis_client = get_or_reconnect_redis()
                    
                    # Send game_start message when new round starts with distributed lock
                    # STRICT lock: requires Redis to prevent duplicates in multi-process setups
                    start_lock_key = f'game_start_sent_{round_obj.round_id}'
                    start_lock_acquired = False
                    if redis_client:
                        try:
                            start_lock_acquired = redis_client.set(start_lock_key, '1', ex=300, nx=True)
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f'Redis connection error during game_start: {e}'))
                            redis_client = get_or_reconnect_redis()

                    if channel_layer and start_lock_acquired:
                        try:
                            # Pre-serialize for high performance
                            game_start_message = {
                                'type': 'game_start',
                                'round_id': round_obj.round_id,
                                'status': 'BETTING',
                                'timer': 1,
                                'is_rolling': False,
                            }
                            game_start_payload = json.dumps(game_start_message)

                            async_to_sync(channel_layer.group_send)(
                                'game_room',
                                {
                                    'type': 'broadcast_raw',
                                    'payload': game_start_payload,
                                }
                            )
                            just_sent_game_start = True
                        except Exception:
                            pass
                    
                    logger.info(f"New round created: {round_obj.round_id}")
                    self.stdout.write(self.style.SUCCESS(f'New round started: {round_obj.round_id}'))
                else:
                    # Calculate timer from elapsed time (1-round_end_time, not 0-(round_end_time-1))
                    # Use the same 'now' from the cleanup check above to ensure consistency
                    elapsed = (now - round_obj.start_time).total_seconds()
                    
                    # If round is older than round_end_time seconds, complete it and create new one
                    if elapsed >= round_end_time:
                        # Mark old round as completed first to get the end_time
                        # Wrap in try-except to prevent blocking on DB errors
                        try:
                            round_obj.status = 'COMPLETED'
                            round_obj.end_time = now
                            round_obj.save()
                        except Exception as db_err:
                            self.stdout.write(self.style.WARNING(f'Failed to save round completion (non-critical): {db_err}'))
                            # Continue anyway - Redis will handle the new round
                        
                        # Send game_end message with time and date (with distributed lock)
                        # STRICT lock: requires Redis for coordination
                        end_lock_key = f'game_end_sent_{round_obj.round_id}'
                        end_lock_acquired = False
                        if redis_client:
                            try:
                                end_lock_acquired = redis_client.set(end_lock_key, '1', ex=300, nx=True)
                                
                                # CLEANUP REDIS EXPOSURE KEYS
                                # 1. Get final stats from Redis before deleting
                                pipe = redis_client.pipeline()
                                pipe.get(f"round:{round_obj.round_id}:total_exposure")
                                pipe.get(f"round:{round_obj.round_id}:bet_count")
                                results = pipe.execute()
                                
                                # 2. Sync to DB if available
                                if results[0] or results[1]:
                                    try:
                                        round_obj.total_amount = Decimal(str(results[0] or "0.00"))
                                        round_obj.total_bets = int(results[1] or 0)
                                        round_obj.save(update_fields=['total_amount', 'total_bets'])
                                    except: pass
                                
                                # 3. Delete keys
                                redis_client.delete(
                                    f"round:{round_obj.round_id}:total_exposure",
                                    f"round:{round_obj.round_id}:user_exposure",
                                    f"round:{round_obj.round_id}:bet_count",
                                    f"round_total_bets:{round_obj.round_id}",
                                    f"round_total_amount:{round_obj.round_id}"
                                )
                                logger.info(f"Cleaned up Redis exposure keys for round {round_obj.round_id}")
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f'Redis connection error during game_end lock/cleanup: {e}'))
                                redis_client = get_or_reconnect_redis()

                        if channel_layer and end_lock_acquired:
                            try:
                                # Pre-serialize for high performance
                                game_end_message = {
                                    'type': 'game_end',
                                    'round_id': round_obj.round_id,
                                    'status': 'COMPLETED',
                                    'timer': round_end_time,
                                    'is_rolling': False,
                                    'end_time': round_obj.end_time.isoformat(),
                                    'start_time': round_obj.start_time.isoformat(),
                                    'result_time': round_obj.result_time.isoformat() if round_obj.result_time else None,
                                }
                                game_end_payload = json.dumps(game_end_message)

                                async_to_sync(channel_layer.group_send)(
                                    'game_room',
                                    {
                                        'type': 'broadcast_raw',
                                        'payload': game_end_payload,
                                    }
                                )
                                self.stdout.write(self.style.SUCCESS(f'📤 Sent game_end message for round {round_obj.round_id}'))
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f'❌ Failed to send game_end: {e}'))
                        
                        # Create new round - wrap in try-except to prevent blocking
                        try:
                            round_obj = GameRound.objects.create(
                                round_id=f"R{int(now.timestamp())}",
                                status='BETTING',
                                betting_close_seconds=betting_close_time,
                                dice_roll_seconds=dice_rolling_time,
                                dice_result_seconds=dice_result_time,
                                round_end_seconds=round_end_time
                            )
                        except Exception as db_err:
                            self.stdout.write(self.style.ERROR(f'Failed to create new round after completion (will retry): {db_err}'))
                            # Close stale connections and continue - will retry next iteration
                            from django.db import connections
                            connections.close_all()
                            round_obj = None
                            # Continue loop - timer will keep running
                        # Reset flags for new round
                        round_obj._dice_roll_sent = False
                        round_obj._dice_result_sent = False
                        last_broadcast_timer = -1  # Reset for new round
                        # Clear Redis flags for previous round if any
                        if redis_client:
                            try:
                                redis_client.delete(f'dice_result_sent_{round_obj.round_id}')
                            except Exception:
                                pass
                        timer = 1  # Start new round at 1
                        status = 'BETTING'
                        
                        # Send game_start message for new round
                        if channel_layer:
                            try:
                                async_to_sync(channel_layer.group_send)(
                                    'game_room',
                                    {
                                        'type': 'game_start',
                                        'round_id': round_obj.round_id,
                                        'status': 'BETTING',
                                        'timer': 1,
                                        'is_rolling': False,
                                    }
                                )
                                just_sent_game_start = True
                            except Exception:
                                pass
                        round_data = {
                            'round_id': round_obj.round_id,
                            'status': 'BETTING',
                            'start_time': round_obj.start_time.isoformat(),
                            'timer': 1,
                        }
                        # Update Redis with new round (use pipeline for efficient batch writes)
                        if redis_client:
                            pipe = redis_client.pipeline()
                            pipe.set('current_round', json.dumps(round_data), ex=5)
                            pipe.set('round_timer', '1', ex=5)
                            pipe.execute()  # Execute both writes in one round trip
                        logger.info(f"New round created: {round_obj.round_id}")
                        self.stdout.write(self.style.SUCCESS(f'New round started: {round_obj.round_id}'))
                    else:
                        # Calculate timer using helper (1 to round_end_time)
                        timer = calculate_current_timer(round_obj.start_time, round_end_time)
                        
                        # Determine status based on timer value
                        if timer <= betting_close_time:
                            # e.g., 1-30 seconds: BETTING
                            status = 'BETTING'
                        elif timer < dice_result_time:
                            # e.g., 31-50 seconds: CLOSED
                            status = 'CLOSED'
                        elif timer <= round_end_time:
                            # e.g., 51-80 seconds: RESULT
                            status = 'RESULT'
                        else:
                            # Fallback
                            status = 'RESULT'
                        
                        # Update database status if it doesn't match
                        # Wrap in try-except to prevent blocking on DB errors
                        if round_obj.status != status:
                            try:
                                round_obj.status = status
                                if status == 'CLOSED' and not round_obj.betting_close_time:
                                    round_obj.betting_close_time = now
                                elif status == 'RESULT' and not round_obj.result_time:
                                    round_obj.result_time = now
                                # Note: We don't save here to reduce DB load - status is in Redis
                            except Exception as db_err:
                                # DB error - log but continue
                                if iteration_count % 30 == 0:  # Only log every 30 iterations
                                    self.stdout.write(self.style.WARNING(f'Status update error (non-critical): {db_err}'))
                        
                        # Build round_data
                        round_data = {
                            'round_id': round_obj.round_id,
                            'status': status,
                            'start_time': round_obj.start_time.isoformat(),
                            'timer': timer,
                        }
                        
                        # Update Redis with current timer (use pipeline for efficient batch writes)
                        if redis_client:
                            try:
                                pipe = redis_client.pipeline()
                                pipe.set('round_timer', str(timer), ex=60)
                                pipe.set('current_round', json.dumps(round_data), ex=60)
                                pipe.execute()  # Execute both writes in one round trip
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f'Redis write error: {e}, reconnecting...'))
                                redis_client = get_or_reconnect_redis()
                
                # Track dice_roll message to prevent duplicates
                dice_roll_sent_this_round = getattr(round_obj, '_dice_roll_sent', False)
                
                # Send dice_roll event at dice_rolling_time (e.g., 19s) to START animation
                # This should happen BEFORE dice_result is set, so the animation can start
                if timer == dice_rolling_time and channel_layer and not dice_roll_sent_this_round and dice_rolling_time < dice_result_time:
                    try:
                        # Distributed lock for dice_roll - STRICT (requires Redis)
                        roll_lock_key = f'dice_roll_sent_{round_obj.round_id}'
                        roll_lock_acquired = False
                        if redis_client:
                            try:
                                roll_lock_acquired = redis_client.set(roll_lock_key, '1', ex=60, nx=True)
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f'Redis connection error during dice_roll: {e}'))
                                redis_client = get_or_reconnect_redis()

                        if roll_lock_acquired:
                            # Pre-serialize for high performance
                            dice_roll_message = {
                                'type': 'dice_roll',
                                'round_id': round_obj.round_id,
                                'timer': timer,
                                'dice_roll_time': dice_rolling_time,
                                'is_rolling': True,
                            }
                            dice_roll_payload = json.dumps(dice_roll_message)

                            # Send dice_roll event to trigger animation
                            async_to_sync(channel_layer.group_send)(
                                'game_room',
                                {
                                    'type': 'broadcast_raw',
                                    'payload': dice_roll_payload,
                                }
                            )
                            # Mark as sent to avoid duplicates (local + distributed)
                            round_obj._dice_roll_sent = True
                            self.stdout.write(self.style.SUCCESS(f'📤 Sent dice_roll at timer {timer}s (animation start)'))
                        elif redis_client and not roll_lock_acquired:
                            # Lock exists, another process handled it
                            round_obj._dice_roll_sent = True
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'❌ Failed to send dice_roll: {e}'))
                
                # Handle special cases for RESULT status
                if status == 'RESULT':
                    dice_values_for_broadcast = None
                    
                    # Check if dice values are actually set (dice_1 through dice_6)
                    dice_values_missing = any(
                        getattr(round_obj, f'dice_{i}', None) is None 
                        for i in range(1, 7)
                    )
                    
                    # Auto-roll if dice_result is missing OR if any individual dice values are missing
                    # Check when timer >= dice_result_time (not just ==) to handle missed checks
                    if timer >= dice_result_time:
                        # If values are missing, auto-roll
                        if not round_obj.dice_result or dice_values_missing:
                            # Check dice mode – regardless of mode, ensure dice roll happens
                            dice_mode = get_dice_mode()
                            dice_values, result = generate_random_dice_values()
                            apply_dice_values_to_round(round_obj, dice_values)
                            for index, value in enumerate(dice_values, start=1):
                                round_data[f'dice_{index}'] = value

                            round_obj.dice_result = result
                            if not round_obj.result_time:
                                round_obj.result_time = timezone.now()
                            round_data['dice_result'] = result
                            dice_values_for_broadcast = dice_values

                            # CRITICAL: Save round_obj to database to persist dice values
                            # Wrap in try-except to prevent blocking on DB errors
                            try:
                                round_obj.save()

                                # Create dice result record
                                DiceResult.objects.update_or_create(
                                    round=round_obj,
                                    defaults={'result': result or "0"}
                                )

                                # Calculate payouts
                                calculate_payouts(round_obj, dice_result=result, dice_values=dice_values)
                            except Exception as db_err:
                                self.stdout.write(self.style.WARNING(f'Failed to save dice result/payouts (non-critical): {db_err}'))
                                # Continue - timer should keep running even if DB save fails

                            logger.info(f"Dice rolled automatically (random mode) at {timer}s for round {round_obj.round_id}: Result={result}")
                            self.stdout.write(self.style.SUCCESS(f'🎲 Dice rolled automatically (random mode) at {timer}s: {result}'))
                        
                        # If dice were already set (e.g., by admin pre-set), but payouts haven't been calculated for this round
                        # We use the dice_result_sent lock to ensure this only runs once at dice_result_time
                        if timer == dice_result_time:
                            # Extract dice values and calculate payouts for the pre-set dice
                            existing_result = round_obj.dice_result
                            dice_values_for_payout = [
                                getattr(round_obj, f'dice_{i}') for i in range(1, 7)
                            ]
                            
                            if all(v is not None for v in dice_values_for_payout):
                                calculate_payouts(round_obj, dice_result=existing_result, dice_values=dice_values_for_payout)
                                self.stdout.write(self.style.SUCCESS(f'💰 Payouts calculated for pre-set dice at {timer}s: {existing_result}'))
                            
                            dice_values_for_broadcast = dice_values_for_payout

                        # Ensure dice values are available for broadcast if not already set
                        if dice_values_for_broadcast is None:
                            existing_result = round_obj.dice_result
                            dice_values_for_broadcast = extract_dice_values(
                                round_obj, round_data, fallback=existing_result
                            )
                    else:
                        # Timer not at dice_result_time yet; still ensure dice values are ready for broadcast
                        # OR dice values are already set
                        existing_result = round_obj.dice_result
                        dice_values_for_broadcast = extract_dice_values(
                            round_obj, round_data, fallback=existing_result
                        )
                    
                    # If dice values exist in database but not in round_data, sync them
                    if round_obj.dice_1 is not None:
                        for index in range(1, 7):
                            dice_value = getattr(round_obj, f'dice_{index}', None)
                            if dice_value is not None:
                                round_data[f'dice_{index}'] = dice_value

                    # Send dice_result message ONCE when timer reaches dice_result_time
                    # Use Redis SET NX (set if not exists) as an atomic lock to prevent duplicates
                    # CRITICAL: Check Redis FIRST before any other checks
                    dice_result_lock_key = f'dice_result_sent_{round_obj.round_id}'
                    dice_result_already_sent = False
                    
                    # Check Redis flag first (most reliable)
                    if redis_client:
                        try:
                            existing_flag = redis_client.get(dice_result_lock_key)
                            if existing_flag:
                                dice_result_already_sent = True
                                # Sync instance attribute
                                round_obj._dice_result_sent = True
                        except Exception:
                            pass
                    
                    # Only proceed if timer matches and we haven't sent yet
                    if timer == dice_result_time and channel_layer and round_obj.dice_result and not dice_result_already_sent:
                        try:
                            # CRITICAL: Try to acquire lock using SET NX (atomic operation)
                            # This ensures only ONE process can set the flag and send the message
                            lock_acquired = False
                            if redis_client:
                                try:
                                    # SET with NX returns True if key was set, False if key already exists
                                    lock_acquired = redis_client.set(
                                        dice_result_lock_key, 
                                        '1', 
                                        ex=300,  # Expire after 5 minutes
                                        nx=True  # Only set if key doesn't exist (atomic)
                                    )
                                except Exception as e:
                                    self.stdout.write(self.style.WARNING(f'Redis lock error: {e}'))
                            
                            # ONLY send if we successfully acquired the lock
                            if lock_acquired:
                                if dice_values_for_broadcast is None:
                                    dice_values_for_broadcast = extract_dice_values(
                                        round_obj, round_data, fallback=round_obj.dice_result
                                    )
                                
                                # Pre-serialize the message for high performance
                                dice_result_message = {
                                    'type': 'dice_result',
                                    'result': round_obj.dice_result,
                                    'round_id': round_obj.round_id,
                                    'timer': timer,
                                    'dice_values': dice_values_for_broadcast,
                                    'is_rolling': False,
                                }
                                dice_result_payload = json.dumps(dice_result_message)

                                # Send dice_result event to display the result
                                async_to_sync(channel_layer.group_send)(
                                    'game_room',
                                    {
                                        'type': 'broadcast_raw',
                                        'payload': dice_result_payload,
                                    }
                                )
                                # Mark as sent
                                round_obj._dice_result_sent = True
                                self.stdout.write(self.style.SUCCESS(f'📤 Sent dice_result at timer {timer}s (result display)'))
                            else:
                                # Lock not acquired - already sent by another iteration
                                round_obj._dice_result_sent = True
                                self.stdout.write(self.style.WARNING(f'⚠️ Dice_result already sent (lock exists) for round {round_obj.round_id} at timer {timer}s'))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'❌ Failed to send dice_result: {e}'))
                            import traceback
                            traceback.print_exc()
                    # Sync instance attribute if Redis flag exists (handles missed exact second)
                    elif timer > dice_result_time:
                        if redis_client:
                            try:
                                redis_flag = redis_client.get(f'dice_result_sent_{round_obj.round_id}')
                                if redis_flag:
                                    # Already sent, mark instance attribute
                                    round_obj._dice_result_sent = True
                            except Exception:
                                pass
                
                # CRITICAL: Only sync totals from Redis every 5 seconds to reduce DB load
                # Wrap in try-except to prevent blocking on DB errors
                if iteration_count % 5 == 0 and redis_client and round_obj:
                    try:
                        total_bets_val = redis_client.get(f"round_total_bets:{round_obj.round_id}")
                        if total_bets_val:
                            round_obj.total_bets = int(total_bets_val)
                        
                        total_amount_val = redis_client.get(f"round_total_amount:{round_obj.round_id}")
                        if total_amount_val:
                            from decimal import Decimal
                            round_obj.total_amount = Decimal(str(total_amount_val))
                        
                        # Only save if we updated something - wrap in try-except
                        try:
                            round_obj.save(update_fields=['total_bets', 'total_amount'])
                        except Exception as db_err:
                            # DB save failed - log but don't block timer
                            if iteration_count % 30 == 0:  # Only log every 30 iterations to avoid spam
                                self.stdout.write(self.style.WARNING(f'DB save error (non-critical): {db_err}'))
                    except Exception as e:
                        # Redis or other error - log but don't block
                        if iteration_count % 30 == 0:  # Only log every 30 iterations
                            self.stdout.write(self.style.WARNING(f'Redis totals sync error (non-critical): {e}'))

                # We already save round_obj in specific places when status or dice change.
                # Removing the global round_obj.save() to significantly reduce DB load.
                # round_obj.save()  <-- REMOVED
                
                # Update Redis with latest dice values if they exist in database
                if redis_client and round_obj.dice_1 is not None:
                    try:
                        # Update round_data with dice values from database
                        for index in range(1, 7):
                            dice_value = getattr(round_obj, f'dice_{index}', None)
                            if dice_value is not None:
                                round_data[f'dice_{index}'] = dice_value
                        # Save updated round_data to Redis
                        pipe = redis_client.pipeline()
                        pipe.set('current_round', json.dumps(round_data), ex=60)
                        pipe.execute()
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Redis dice values update error: {e}, reconnecting...'))
                        redis_client = get_or_reconnect_redis()
                
                # Ensure timer is in valid range (1-round_end_time)
                if timer < 1:
                    timer = 1
                elif timer > round_end_time:
                    timer = round_end_time
                
                # Broadcast timer update ONCE per loop iteration (no duplicates)
                # Skip timer message if we just sent game_start to avoid duplicates
                # Skip timer message at round_end_time seconds (end of round)
                if timer > 0:
                    # CRITICAL: Check against last_broadcast_timer to prevent duplicates
                    # AND use Redis distributed lock for multi-process coordination
                    # Lock key includes round_id and timer value
                    timer_lock_key = f'timer_sent_{round_obj.round_id}_{timer}'
                    lock_acquired = False
                    
                    if redis_client:
                        try:
                            # Try to acquire lock using SET NX (atomic operation)
                            # ex=5: lock expires in 5 seconds (plenty for 1s loop)
                            # nx=True: only set if key doesn't exist
                            lock_acquired = redis_client.set(
                                timer_lock_key,
                                '1',
                                ex=60,
                                nx=True
                            )
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f'Redis connection error during timer lock: {e}'))
                            redis_client = get_or_reconnect_redis()
                            # NO fallback to True - coordination requires shared memory (Redis)
                            lock_acquired = False
                    else:
                        # Redis not available - log warning every 10 iterations
                        if iteration_count % 10 == 0:
                            self.stdout.write(self.style.WARNING('⚠️ Redis not available for distributed lock - coordination DISABLED'))
                        # ONLY allow broadcast if we are the only process (local state)
                        # This avoids massive flooding in multi-process environments
                        lock_acquired = (timer != last_broadcast_timer)

                    if not just_sent_game_start and timer != round_end_time and lock_acquired:
                        last_broadcast_timer = timer  # Update last broadcast
                        # Timer message - clean message with only timer, status, and round_id
                        # Changed type to 'timer' to match consumer handler exactly
                        timer_message = {
                            'type': 'timer',
                            'timer': timer,
                            'status': status,
                            'round_id': round_obj.round_id if round_obj else None,
                            'is_rolling': (dice_rolling_time <= timer < dice_result_time),
                        }
                    
                        if channel_layer:
                            try:
                                # Pre-serialize the message for high performance
                                timer_payload = json.dumps(timer_message)
                                
                                # Use send_nowait=False to prevent blocking on full channels
                                # This ensures messages are queued even if channel is busy
                                async_to_sync(channel_layer.group_send)(
                                    'game_room',
                                    {
                                        'type': 'broadcast_raw',
                                        'payload': timer_payload
                                    }
                                )
                                # Log every 10 seconds to avoid spam
                                if timer % 10 == 0:
                                    self.stdout.write(self.style.SUCCESS(f'📤 Broadcast timer: {timer}s, Status: {status}'))
                            except Exception as e:
                                # Don't let broadcast errors stop the timer loop
                                logger.error(f"Failed to broadcast at {timer}s: {e}")
                                if timer % 30 == 0:  # Only log errors every 30 seconds to avoid spam
                                    self.stdout.write(self.style.ERROR(f'❌ Failed to broadcast: {e}'))
                                # Try to reconnect channel layer silently
                                try:
                                    channel_layer = get_or_reconnect_channel_layer()
                                except Exception:
                                    pass  # Silently fail, will retry next iteration
                    elif redis_client and not lock_acquired:
                        # Lock already exists in Redis
                        if timer != last_broadcast_timer and not just_sent_game_start and timer != round_end_time:
                            # This means another process got the lock first
                            if timer % 10 == 0:
                                self.stdout.write(self.style.WARNING(f'⚠️ Timer {timer}s already sent by another process, skipping...'))
                            last_broadcast_timer = timer # Sync local state to skip redundant lock attempts
                
                round_id = round_obj.round_id if round_obj else 'N/A'
                self.stdout.write(f"Timer: {timer}s, Status: {status}, Round: {round_id}")
                
                # IMPORTANT: DO NOT close database connections manually!
                # Django automatically manages connections through its connection pool.
                # Manually closing connections can cause:
                # 1. Data loss if transactions are interrupted
                # 2. Connection pool exhaustion
                # 3. Race conditions
                # Django will automatically close idle connections and reuse them.
                
                # Calculate sleep time to maintain consistent 1-second intervals
                # CRITICAL: Always ensure minimum sleep to prevent rapid-fire messages and timer getting stuck
                iteration_end = time.time()
                elapsed_in_iteration = iteration_end - iteration_start

                # Simplified sleep calculation: Always aim for ~1 second sleep
                # If operations took longer than 1 second, sleep less (catch up)
                # But always sleep at least 0.8 seconds to prevent continuous rapid messages
                # This ensures the timer doesn't get stuck or run too fast
                if elapsed_in_iteration < 1.0:
                    # Operations finished quickly, sleep for the remainder of 1 second
                    sleep_time = 1.0 - elapsed_in_iteration
                    # Ensure minimum sleep of 0.8 seconds to prevent rapid iterations
                    sleep_time = max(0.8, sleep_time)
                else:
                    # Operations took longer than 1 second, sleep briefly to prevent CPU spinning
                    sleep_time = 0.1

                # Cap sleep at 1.2 seconds max to prevent long delays and ensure timer keeps moving
                sleep_time = min(sleep_time, 1.2)
                time.sleep(sleep_time)

                iteration_count += 1
                if iteration_count % 60 == 0:
                    logger.debug(f"Game timer loop iteration {iteration_count}")
            except Exception as e:
                logger.exception(f"Critical error in game timer loop: {e}")
                self.stdout.write(self.style.ERROR(f'Error: {e}'))
                import traceback
                traceback.print_exc()
                
                # IMPORTANT: DO NOT close database connections on error!
                # Django will handle connection cleanup automatically.
                # Closing connections manually can cause data loss.
                
                # Reconnect to channel layer if it failed
                try:
                    channel_layer = get_or_reconnect_channel_layer()
                    if channel_layer:
                        self.stdout.write(self.style.SUCCESS('✅ Reconnected to channel layer'))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Failed to reconnect channel layer: {e}'))
                
                time.sleep(1)

