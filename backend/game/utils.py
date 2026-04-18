import random
import json
from collections import Counter


def format_indian_int(value):
    """Format integer with Indian-style commas (e.g. 12,34,567). Returns str."""
    if value is None:
        return '0'
    try:
        n = int(value)
    except (TypeError, ValueError):
        return '0'
    s = str(abs(n))
    if not s:
        return '0'
    if len(s) <= 3:
        return ('-' if n < 0 else '') + s
    groups = [s[-3:]]
    s = s[:-3]
    while s:
        groups.insert(0, s[-2:])
        s = s[:-2]
    return ('-' if n < 0 else '') + ','.join(groups)
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from .models import GameRound, GameSettings

try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
except Exception:
    IST = None


def get_leaderboard_period_date(dt=None):
    """
    Return the leaderboard period date (IST) for the given datetime.
    Period is 23:00 IST to next 23:00 IST; period_date is the date of the period start.
    dt: timezone-aware or naive datetime; defaults to now (UTC).
    """
    if dt is None:
        dt = timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt) if IST else dt
    now_ist = dt.astimezone(IST) if IST and dt.tzinfo else dt
    if not IST:
        return now_ist.date()
    period_anchor = now_ist.replace(hour=23, minute=0, second=0, microsecond=0)
    if now_ist >= period_anchor:
        period_start = period_anchor
    else:
        period_start = period_anchor - timedelta(days=1)
    return period_start.date()


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
            # Prefer the engine's primary key first (more reliable than legacy round_timer).
            state_raw = redis_client.get('current_game_state')
            if state_raw:
                try:
                    round_data = json.loads(state_raw)
                except Exception:
                    round_data = None

                if isinstance(round_data, dict) and round_data.get('round_id'):
                    try:
                        round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                    except GameRound.DoesNotExist:
                        round_obj = None

                    status = round_data.get('status', status) if isinstance(round_data, dict) else status

                    # Engine publishes a monotonic "timer" (counts up from 1). Use it if present.
                    try:
                        t = int(round_data.get('timer', 0))
                        timer = t if t >= 0 else 0
                    except Exception:
                        timer = 0

                    # If we got a usable state, return early.
                    if timer > 0:
                        # Even if the DB row is briefly unavailable, the engine timer is still useful for UI.
                        return round_obj, timer, status, round_data

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
                    # Prefer explicit timer in payload if present; otherwise legacy round_timer.
                    try:
                        if isinstance(round_data, dict) and round_data.get('timer') is not None:
                            timer = int(round_data.get('timer') or 0)
                        else:
                            timer = int(redis_client.get('round_timer') or '0')
                    except Exception:
                        timer = 0
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

    if round_obj and timer == 0:
        # Avoid mid-round "0" glitches in admin UIs.
        timer = 1

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
    """
    Return dice values from the round object or cached round data.
    fallback: Only use if it's a single integer 1-6. Never use dice_result string
    (e.g. "1, 3") as fallback - that represents winning numbers, not individual dice.
    """
    values = []
    # Only use fallback if it's a valid single dice value (1-6)
    valid_fallback = None
    if fallback is not None:
        try:
            n = int(fallback) if not isinstance(fallback, int) else fallback
            if 1 <= n <= 6:
                valid_fallback = n
        except (ValueError, TypeError):
            pass
    for index in range(1, 7):
        value = getattr(round_obj, f'dice_{index}', None)
        if value is None and round_data:
            value = round_data.get(f'dice_{index}')
        if value is None and valid_fallback is not None:
            value = valid_fallback
        values.append(value)
    return values


def calculate_current_timer(start_time, round_end_time=None):
    """
    Calculate current timer value (1-indexed, capped at round_end_time).
    Consistent with start_game_timer.py and game_engine_v3.
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
    Deprecated: The new GameEngine handles its own state in 'current_game_state'.
    """
    return True


def sync_database_to_redis(redis_client):
    """
    Deprecated: The new GameEngine handles its own state in 'current_game_state'.
    """
    return True


# In-memory cache for game settings to reduce DB load
_SETTINGS_CACHE = {}
_SETTINGS_CACHE_TIME = {}


def clear_game_setting_cache(keys=None):
    """Clear cache for given keys, or all keys if None. Call after updating settings."""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    if keys is None:
        _SETTINGS_CACHE.clear()
        _SETTINGS_CACHE_TIME.clear()
    else:
        for k in keys:
            _SETTINGS_CACHE.pop(k, None)
            _SETTINGS_CACHE_TIME.pop(k, None)


def get_game_setting(key, default=None):
    """
    Get a game setting from the database, with fallback to settings.py defaults.
    Uses in-memory caching to reduce database load.
    """
    now = timezone.now().timestamp()
    
    # Check in-memory cache (valid for 30 seconds)
    if key in _SETTINGS_CACHE and (now - _SETTINGS_CACHE_TIME.get(key, 0)) < 30:
        return _SETTINGS_CACHE[key]

    try:
        # Query directly using values_list to bypass any ORM instance caching
        result = GameSettings.objects.filter(key=key).values_list('value', flat=True).first()
        if result is None:
            raise GameSettings.DoesNotExist(f"GameSettings matching query does not exist.")
        value = result
        
        # Convert to int for numeric settings
        numeric_keys = [
            'BETTING_CLOSE_TIME', 'DICE_ROLL_TIME', 'DICE_RESULT_TIME', 'ROUND_END_TIME',
            'BETTING_DURATION', 'RESULT_SELECTION_DURATION', 
            'RESULT_DISPLAY_DURATION', 'TOTAL_ROUND_DURATION',
            'RESULT_ANNOUNCE_TIME', 'MAX_BET'
        ]
        if key in numeric_keys:
            try:
                value = int(value)
            except (ValueError, TypeError):
                pass
        
        # Update cache
        _SETTINGS_CACHE[key] = value
        _SETTINGS_CACHE_TIME[key] = now
        
        return value
    except GameSettings.DoesNotExist:
        # Fallback to settings.py defaults
        game_settings = getattr(settings, 'GAME_SETTINGS', {})
        value = game_settings.get(key, default)
        
        # Update cache for fallback too
        _SETTINGS_CACHE[key] = value
        _SETTINGS_CACHE_TIME[key] = now
        
        return value
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
        'RESULT_ANNOUNCE_TIME', 'MAX_BET'
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


def get_redis_client():
    """
    Get a Redis client for the configured host.
    Prefer REDIS_POOL from settings so we reuse connections (avoids slow new TCP per call).

    IMPORTANT:
    This project uses Redis as a single source of truth for game state + betting.
    Using "failover" across multiple independent Redis instances can cause split-brain
    (different round/status/bet-stream keys), which breaks betting under load.
    """
    import redis
    import logging
    logger = logging.getLogger('game')

    try:
        pool = getattr(settings, 'REDIS_POOL', None)
        if pool:
            client = redis.Redis(connection_pool=pool)
            client.ping()
            return client
    except Exception as e:
        logger.warning("Redis (pool) connection failed: %s", e)

    host = getattr(settings, 'REDIS_HOST', '72.61.254.74')
    password = getattr(settings, 'REDIS_PASSWORD', 'Gunduata@123')
    port = int(getattr(settings, 'REDIS_PORT', 6379))
    db = int(getattr(settings, 'REDIS_DB', 0))

    try:
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis connection failed to {host}: {e}")
    return None
