import random
import json
from collections import Counter
from django.utils import timezone
from django.conf import settings
from .models import GameRound, GameSettings


def get_current_round_state(redis_client):
    """
    Get the current round state from Redis or Database.
    Handles staleness checks and provides a consistent interface.
    Returns: (round_obj, timer, status, round_data_dict)
    """
    round_obj = None
    timer = 0
    status = 'WAITING'
    round_data = None

    if redis_client:
        try:
            round_data_raw = redis_client.get('current_round')
            if round_data_raw:
                round_data = json.loads(round_data_raw)
                
                # Check for staleness
                is_stale = False
                if 'start_time' in round_data:
                    from datetime import datetime
                    try:
                        start_time = datetime.fromisoformat(round_data['start_time'])
                        if timezone.is_aware(timezone.now()) and not timezone.is_aware(start_time):
                            start_time = timezone.make_aware(start_time)
                        
                        elapsed = (timezone.now() - start_time).total_seconds()
                        round_end_time = get_game_setting('ROUND_END_TIME', 80)
                        if elapsed > round_end_time + 10:  # 10s buffer
                            is_stale = True
                    except (ValueError, TypeError):
                        pass
                
                if not is_stale:
                    timer = int(redis_client.get('round_timer') or '0')
                    status = round_data.get('status', 'WAITING')
                    try:
                        round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                    except GameRound.DoesNotExist:
                        pass
                else:
                    # Clear stale Redis data
                    redis_client.delete('current_round')
                    redis_client.delete('round_timer')
                    round_data = None
        except Exception:
            pass

    # Fallback to database
    if not round_obj:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if round_obj:
            status = round_obj.status
            if round_obj.start_time:
                elapsed = (timezone.now() - round_obj.start_time).total_seconds()
                timer = int(elapsed) % get_game_setting('ROUND_END_TIME', 80)
            
            # Reconstruct round_data dict for consistency
            round_data = {
                'round_id': round_obj.round_id,
                'status': round_obj.status,
                'dice_1': round_obj.dice_1,
                'dice_2': round_obj.dice_2,
                'dice_3': round_obj.dice_3,
                'dice_4': round_obj.dice_4,
                'dice_5': round_obj.dice_5,
                'dice_6': round_obj.dice_6,
                'dice_result': round_obj.dice_result,
                'dice_result_list': round_obj.dice_result_list,
            }

    return round_obj, timer, status, round_data


def generate_random_dice_values():
    """Generate six random dice values and determine the winning number."""
    dice_values = [random.randint(1, 6) for _ in range(6)]
    winning_number = determine_winning_number(dice_values)
    return dice_values, winning_number


def determine_winning_number(dice_values):
    """
    Determine the winning number(s) for display.
    Rule: A number must appear at least 2 times to win.
    Returns all winning numbers as a comma-separated string.
    """
    if not dice_values:
        return None
    
    # Convert all values to int to ensure consistent counting
    try:
        dice_values = [int(v) for v in dice_values if v is not None]
    except (ValueError, TypeError):
        pass
        
    counts = Counter(dice_values)
    # Find numbers that appeared 2 or more times
    winners = sorted([num for num, count in counts.items() if count >= 2])
    
    if not winners:
        return "0"  # Return "0" to indicate No Winner (prevents Null IntegrityError)
        
    return ", ".join(map(str, winners))


def apply_dice_values_to_round(round_obj, dice_values):
    """Persist six dice values onto the GameRound instance and recalculate dice_result."""
    if len(dice_values) != 6:
        raise ValueError('dice_values must contain 6 entries')
    for index, value in enumerate(dice_values, start=1):
        setattr(round_obj, f'dice_{index}', value)
    # Always recalculate dice_result from the actual dice values
    round_obj.dice_result = determine_winning_number(dice_values)


def extract_dice_values(round_obj, round_data=None, fallback=None):
    """Return dice values from the round object or cached round data."""
    values = []
    for index in range(1, 7):
        value = getattr(round_obj, f'dice_{index}', None)
        if value is None and round_data:
            value = round_data.get(f'dice_{index}')
        if value is None:
            value = fallback
        values.append(value)
    return values


def calculate_current_timer(start_time, round_end_time=None):
    """
    Calculate current timer value (1-indexed, capped at round_end_time).
    Consistent with start_game_timer.py and consumers.py.
    """
    if not start_time:
        return 1
    
    if round_end_time is None:
        round_end_time = get_game_setting('ROUND_END_TIME', 80)
        
    elapsed = (timezone.now() - start_time).total_seconds()
    timer = int(elapsed) + 1
    
    if timer > round_end_time:
        timer = round_end_time
    elif timer < 1:
        timer = 1
        
    return timer


def sync_round_to_redis(round_obj, redis_client):
    """
    Sync a GameRound object from database to Redis.
    Calculates timer based on elapsed time since round start.
    """
    if not redis_client or not round_obj:
        return False
    
    try:
        # Get dynamic round_end_time from settings
        round_end_time = get_game_setting('ROUND_END_TIME', 80)
        
        # Calculate timer using helper
        timer = calculate_current_timer(round_obj.start_time, round_end_time)
        
        # Build round data dict
        round_data = {
            'round_id': round_obj.round_id,
            'status': round_obj.status,
            'start_time': round_obj.start_time.isoformat(),
            'timer': timer,
        }
        
        # Add dice result if available
        if round_obj.dice_result:
            round_data['dice_result'] = round_obj.dice_result
        
        # Add individual dice values
        dice_values = extract_dice_values(round_obj)
        for i, value in enumerate(dice_values, start=1):
            if value is not None:
                round_data[f'dice_{i}'] = value
        
        # Update Redis using pipeline for efficient batch writes
        import json
        pipe = redis_client.pipeline()
        pipe.set('current_round', json.dumps(round_data))
        pipe.set('round_timer', str(timer))
        pipe.execute()  # Execute both writes in one round trip
        
        return True
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error syncing round to Redis: {e}")
        return False


def sync_database_to_redis(redis_client):
    """
    Sync the current active round from database to Redis.
    Returns True if successful, False otherwise.
    """
    if not redis_client:
        return False
    
    try:
        # Get current active round from database
        round_obj = GameRound.objects.filter(
            status__in=['BETTING', 'CLOSED', 'RESULT']
        ).order_by('-start_time').first()
        
        if not round_obj:
            # No active round - check if we should create one
            latest_round = GameRound.objects.order_by('-start_time').first()
            if latest_round and latest_round.status == 'COMPLETED':
                # All rounds completed, create new one
                round_obj = GameRound.objects.create(
                    round_id=f"R{int(timezone.now().timestamp())}",
                    status='BETTING',
                    betting_close_seconds=get_game_setting('BETTING_CLOSE_TIME', 30),
                    dice_roll_seconds=get_game_setting('DICE_ROLL_TIME', 7),
                    dice_result_seconds=get_game_setting('DICE_RESULT_TIME', 51),
                    round_end_seconds=get_game_setting('ROUND_END_TIME', 80)
                )
            else:
                return False
        
        return sync_round_to_redis(round_obj, redis_client)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error syncing database to Redis: {e}")
        return False


def get_game_setting(key, default=None):
    """
    Get a game setting from the database, with fallback to settings.py defaults.
    Always reads fresh from database (no caching).
    
    Args:
        key: The setting key (e.g., 'BETTING_CLOSE_TIME')
        default: Default value if not found in database or settings.py
    
    Returns:
        The setting value (converted to int if it's a numeric setting)
    """
    try:
        # Query directly using values_list to bypass any ORM instance caching
        # This ensures we always get the latest value from the database
        # Using values_list avoids creating model instances, which can be cached
        result = GameSettings.objects.filter(key=key).values_list('value', flat=True).first()
        if result is None:
            raise GameSettings.DoesNotExist(f"GameSettings matching query does not exist.")
        value = result
        
        # Convert to int for numeric settings
        numeric_keys = [
            'BETTING_CLOSE_TIME', 'DICE_ROLL_TIME', 'DICE_RESULT_TIME', 'ROUND_END_TIME',
            'BETTING_DURATION', 'RESULT_SELECTION_DURATION', 
            'RESULT_DISPLAY_DURATION', 'TOTAL_ROUND_DURATION',
            'RESULT_ANNOUNCE_TIME'
        ]
        if key in numeric_keys:
            try:
                return int(value)
            except (ValueError, TypeError):
                pass
        
        return value
    except GameSettings.DoesNotExist:
        # Fallback to settings.py defaults
        game_settings = getattr(settings, 'GAME_SETTINGS', {})
        return game_settings.get(key, default)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting game setting {key}: {e}")
        # Fallback to settings.py defaults
        game_settings = getattr(settings, 'GAME_SETTINGS', {})
        return game_settings.get(key, default)


def get_all_game_settings():
    """
    Get all game settings as a dictionary, with fallback to settings.py defaults.
    This is cached for performance - settings don't change frequently.
    """
    result = {}
    defaults = getattr(settings, 'GAME_SETTINGS', {})
    
    # Get all settings from database
    db_settings = GameSettings.objects.all()
    for setting in db_settings:
        result[setting.key] = setting.value
    
    # Fill in any missing settings from defaults
    for key, value in defaults.items():
        if key not in result:
            result[key] = value
    
    # Convert numeric settings to int
    numeric_keys = [
        'BETTING_CLOSE_TIME', 'DICE_ROLL_TIME', 'DICE_RESULT_TIME', 'ROUND_END_TIME',
        'BETTING_DURATION', 'RESULT_SELECTION_DURATION', 
        'RESULT_DISPLAY_DURATION', 'TOTAL_ROUND_DURATION',
        'RESULT_ANNOUNCE_TIME'
    ]
    for key in numeric_keys:
        if key in result:
            try:
                result[key] = int(result[key])
            except (ValueError, TypeError):
                pass
    
    # Handle PAYOUT_RATIOS - keep as dict from defaults (not stored in DB as JSON)
    if 'PAYOUT_RATIOS' not in result and 'PAYOUT_RATIOS' in defaults:
        result['PAYOUT_RATIOS'] = defaults['PAYOUT_RATIOS']
    
    return result
