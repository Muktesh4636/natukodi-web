import json
import logging
import os
import random
import subprocess
from collections import Counter
from decimal import Decimal


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
            'RESULT_ANNOUNCE_TIME', 'MAX_BET',
            'REFERRAL_INSTANT_BONUS_PER_REFEREE',
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

    host = getattr(settings, 'REDIS_HOST', '127.0.0.1')
    password = getattr(settings, 'REDIS_PASSWORD', '') or None
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


_cockfight_dur_log = logging.getLogger('game')


# --- Cock fight round video (duration + broadcast window) ---


def apply_mp4_faststart(file_path: str) -> bool:
    """
    Move moov atom to the front of an MP4/MOV file so browsers can start
    playing immediately without downloading the whole file (no re-encoding).
    Replaces the file in-place. Returns True if the file was remuxed.
    """
    if not file_path or not os.path.isfile(file_path):
        return False
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.mp4', '.m4v', '.mov'):
        return False
    tmp_path = file_path + '.faststart.tmp.mp4'
    try:
        r = subprocess.run(
            [
                'ffmpeg', '-y',
                '-i', file_path,
                '-c', 'copy',
                '-movflags', '+faststart',
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode != 0:
            _cockfight_dur_log.warning('apply_mp4_faststart failed: %s', r.stderr[-500:])
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False
        os.replace(tmp_path, file_path)
        _cockfight_dur_log.info('apply_mp4_faststart: remuxed %s', file_path)
        return True
    except Exception as e:
        _cockfight_dur_log.warning('apply_mp4_faststart exception: %s', e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


def transcode_cockfight_video_hls(rv_pk: int):
    """
    Background: transcode the original video into HLS with three adaptive quality
    levels — 360p, 720p, 1080p — using 2-second segments.

    Output layout (all under MEDIA_ROOT/cockfight_hls/<hls_token>/):
        master.m3u8
        360p/index.m3u8 + seg*.ts
        720p/index.m3u8 + seg*.ts
        1080p/index.m3u8 + seg*.ts

    hls_token is a random UUID stored on the model so the path is unguessable.
    """
    import threading, uuid as _uuid

    def _run():
        try:
            from .models import CockFightRoundVideo
            from django.conf import settings as dj_settings

            rv = CockFightRoundVideo.objects.filter(pk=rv_pk).first()
            if not rv or not rv.video:
                return
            src = rv.video.path
            if not os.path.isfile(src):
                return

            token = _uuid.uuid4().hex
            out_dir = os.path.join(dj_settings.MEDIA_ROOT, 'cockfight_hls', token)
            os.makedirs(os.path.join(out_dir, '360p'), exist_ok=True)
            os.makedirs(os.path.join(out_dir, '720p'), exist_ok=True)
            os.makedirs(os.path.join(out_dir, '1080p'), exist_ok=True)

            master_pl = os.path.join(out_dir, 'master.m3u8')
            seg_pattern = os.path.join(out_dir, '%v', 'seg%03d.ts')
            variant_pattern = os.path.join(out_dir, '%v', 'index.m3u8')

            r = subprocess.run(
                [
                    'ffmpeg', '-y', '-i', src,
                    # Split video into three streams
                    '-filter_complex',
                    '[0:v]split=3[v1][v2][v3];'
                    '[v1]scale=-2:360[v360];'
                    '[v2]scale=-2:720[v720];'
                    '[v3]scale=-2:1080[v1080]',
                    # 360p video
                    '-map', '[v360]', '-map', '0:a',
                    '-c:v:0', 'libx264', '-profile:v:0', 'main', '-level:v:0', '3.1',
                    '-b:v:0', '800k', '-maxrate:v:0', '900k', '-bufsize:v:0', '1600k',
                    '-c:a:0', 'aac', '-b:a:0', '96k',
                    # 720p video
                    '-map', '[v720]', '-map', '0:a',
                    '-c:v:1', 'libx264', '-profile:v:1', 'main', '-level:v:1', '3.1',
                    '-b:v:1', '2500k', '-maxrate:v:1', '2800k', '-bufsize:v:1', '5000k',
                    '-c:a:1', 'aac', '-b:a:1', '128k',
                    # 1080p video
                    '-map', '[v1080]', '-map', '0:a',
                    '-c:v:2', 'libx264', '-profile:v:2', 'high', '-level:v:2', '4.0',
                    '-b:v:2', '5000k', '-maxrate:v:2', '5500k', '-bufsize:v:2', '10000k',
                    '-c:a:2', 'aac', '-b:a:2', '192k',
                    # HLS output
                    '-f', 'hls',
                    '-hls_time', '2',
                    '-hls_playlist_type', 'vod',
                    '-hls_flags', 'independent_segments',
                    '-hls_segment_filename', seg_pattern,
                    '-master_pl_name', 'master.m3u8',
                    '-var_stream_map', 'v:0,a:0,name:360p v:1,a:1,name:720p v:2,a:2,name:1080p',
                    variant_pattern,
                ],
                capture_output=True,
                text=True,
                timeout=7200,
            )
            if r.returncode != 0:
                _cockfight_dur_log.warning('HLS transcode failed for pk=%s: %s', rv_pk, r.stderr[-400:])
                return

            if not os.path.isfile(master_pl):
                _cockfight_dur_log.warning('HLS transcode: master.m3u8 not found for pk=%s', rv_pk)
                return

            CockFightRoundVideo.objects.filter(pk=rv_pk).update(
                hls_ready=True,
                hls_token=token,
            )
            _cockfight_dur_log.info('HLS transcode done for pk=%s → %s', rv_pk, out_dir)
        except Exception as e:
            _cockfight_dur_log.warning('transcode_cockfight_video_hls error pk=%s: %s', rv_pk, e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def probe_video_file_duration_seconds(file_path: str):
    """Return media duration in seconds via ffprobe, or None if unavailable."""
    if not file_path or not os.path.isfile(file_path):
        return None
    try:
        r = subprocess.run(
            [
                'ffprobe',
                '-v',
                'quiet',
                '-show_entries',
                'format=duration',
                '-of',
                'csv=p=0',
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            return None
        return float(r.stdout.strip())
    except Exception as e:
        _cockfight_dur_log.warning('probe_video_file_duration_seconds: %s', e)
        return None


def ensure_cockfight_round_video_duration(rv):
    """
    Persist duration_seconds via ffprobe once when missing (mutates DB).
    Expects CockFightRoundVideo with video file on disk.
    """
    from .models import CockFightRoundVideo

    if getattr(rv, 'duration_seconds', None) is not None:
        return rv
    try:
        path = rv.video.path
    except Exception:
        return rv
    d = probe_video_file_duration_seconds(path)
    if d is not None and d > 0:
        CockFightRoundVideo.objects.filter(pk=rv.pk).update(duration_seconds=d)
        rv.duration_seconds = d
    return rv


def cockfight_consumer_stream_active(rv) -> bool:
    """
    True while JWT viewers may receive the stream URL.

    URL is released 60 seconds BEFORE the scheduled start so clients can
    pre-load the video in the background and have it fully buffered by the
    time the game begins.  URL is removed once start + duration has passed.
    """
    rv = ensure_cockfight_round_video_duration(rv)
    now = timezone.now()
    PRELOAD_WINDOW = timedelta(minutes=1)

    if rv.scheduled_start and now < (rv.scheduled_start - PRELOAD_WINDOW):
        return False

    if rv.duration_seconds is None:
        return True

    dur = timedelta(seconds=float(rv.duration_seconds))
    if rv.scheduled_start:
        wall_end = rv.scheduled_start + dur
    else:
        wall_end = rv.uploaded_at + dur
    return now < wall_end


def cockfight_round_betting_open(rv) -> bool:
    """
    True while bets may still be placed on this round video.

    Betting closes once the match video window ends (scheduled_start + duration, or
    uploaded_at + duration if no schedule). Unlike consumer stream timing, there is no
    pre-load blackout — users may bet before scheduled_start until wall_end.
    """
    if rv is None:
        return False
    rv = ensure_cockfight_round_video_duration(rv)
    now = timezone.now()
    if rv.duration_seconds is None:
        return True
    dur = timedelta(seconds=float(rv.duration_seconds))
    if rv.scheduled_start:
        wall_end = rv.scheduled_start + dur
    else:
        wall_end = rv.uploaded_at + dur
    return now <= wall_end


def resolve_cockfight_session_for_new_bet():
    """
    Pick or create the OPEN CockFightSession that should receive a new bet.

    If the latest OPEN session points at a round whose betting window has ended,
    new bets go to the next CockFightRoundVideo that has no session yet (same rule as
    ``next_cockfight_video_round_for_betting``), reusing an OPEN session for that video
    if one already exists.

    Returns ``(session, error_message)``. ``error_message`` is None on success.
    Caller must run inside ``transaction.atomic()`` with appropriate locking.
    """
    from .models import CockFightSession, CockFightRoundVideo

    def _attach_next_round_session():
        rv_next = next_cockfight_video_round_for_betting()
        if not rv_next:
            return None, (
                'Betting closed for this round. Upload the next cockfight round video before accepting bets.'
            )
        existing = (
            CockFightSession.objects.select_for_update()
            .filter(status='OPEN', video_round_id=rv_next.pk)
            .order_by('-id')
            .first()
        )
        if existing:
            return existing, None
        new_session = CockFightSession.objects.create(status='OPEN', video_round=rv_next)
        return new_session, None

    session = (
        CockFightSession.objects.select_for_update()
        .filter(status='OPEN')
        .order_by('-id')
        .first()
    )

    if session is None:
        rv_next = next_cockfight_video_round_for_betting()
        if not rv_next:
            return None, (
                'Upload the next cockfight round video in admin before accepting bets '
                '(previous round has closed).'
            )
        return CockFightSession.objects.create(status='OPEN', video_round=rv_next), None

    if session.video_round_id is None:
        rv_next = next_cockfight_video_round_for_betting()
        if not rv_next:
            return None, (
                'No cockfight round video available to attach. Upload a round video in admin first.'
            )
        session.video_round = rv_next
        session.save(update_fields=['video_round'])
        return session, None

    rv = CockFightRoundVideo.objects.filter(pk=session.video_round_id).first()
    if not rv:
        rv_next = next_cockfight_video_round_for_betting()
        if not rv_next:
            return None, 'No cockfight round video available to attach. Upload a round video in admin first.'
        session.video_round = rv_next
        session.save(update_fields=['video_round'])
        return session, None

    if cockfight_round_betting_open(rv):
        return session, None

    return _attach_next_round_session()


def cockfight_claimed_video_round_ids():
    """CockFightRoundVideo PKs that already have at least one CockFightSession row."""
    from .models import CockFightSession

    return set(
        CockFightSession.objects.exclude(video_round_id__isnull=True).values_list(
            'video_round_id', flat=True
        )
    )


def next_cockfight_video_round_for_betting():
    """
    Latest uploaded CockFightRoundVideo that does not yet have any CockFightSession.
    Aligns betting round numbers with admin video round IDs (same pk).
    """
    from .models import CockFightRoundVideo

    claimed = cockfight_claimed_video_round_ids()
    qs = CockFightRoundVideo.objects.all()
    if claimed:
        qs = qs.exclude(pk__in=claimed)
    return qs.order_by('-id').first()


# Cock fight Meron/Wala replacement: API uses COCK1 / COCK2 / DRAW (MERON→COCK1, WALA→COCK2 accepted as aliases).
COCKFIGHT_SIDE_ALIASES = {
    'MERON': 'COCK1',
    'WALA': 'COCK2',
}
COCKFIGHT_SIDE_ODDS = {
    'COCK1': Decimal('1.90'),
    'COCK2': Decimal('1.92'),
    'DRAW': Decimal('4.46'),
}


def get_cockfight_side_odds(round_video=None):
    """
    Effective decimal odds per side.

    If ``round_video`` is a ``CockFightRoundVideo`` instance or primary key: COCK1/COCK2 use that
    round's ``odds_cock1`` / ``odds_cock2`` (set when uploading on cockfight round videos admin).

    Otherwise COCK1/COCK2 fall back to Game Settings (COCKFIGHT_ODDS_COCK1 / COCKFIGHT_ODDS_COCK2).

    DRAW is always fixed (see ``COCKFIGHT_SIDE_ODDS``).
    """
    from decimal import InvalidOperation
    from .models import CockFightRoundVideo

    out = {
        'COCK1': COCKFIGHT_SIDE_ODDS['COCK1'],
        'COCK2': COCKFIGHT_SIDE_ODDS['COCK2'],
        'DRAW': COCKFIGHT_SIDE_ODDS['DRAW'],
    }
    lo, hi = Decimal('1'), Decimal('999.99')

    rv = None
    if round_video is not None:
        if isinstance(round_video, CockFightRoundVideo):
            rv = round_video
        else:
            try:
                pk = int(round_video)
            except (TypeError, ValueError):
                pk = None
            if pk:
                rv = CockFightRoundVideo.objects.filter(pk=pk).only('odds_cock1', 'odds_cock2').first()

    if rv is not None:
        for attr, side in (('odds_cock1', 'COCK1'), ('odds_cock2', 'COCK2')):
            val = getattr(rv, attr, None)
            if val is not None:
                try:
                    d = Decimal(str(val))
                    if lo <= d <= hi:
                        out[side] = d
                except (InvalidOperation, TypeError, ValueError):
                    pass
        return out

    for side, gkey in (('COCK1', 'COCKFIGHT_ODDS_COCK1'), ('COCK2', 'COCKFIGHT_ODDS_COCK2')):
        raw = get_game_setting(gkey, str(out[side]))
        try:
            d = Decimal(str(raw).strip().replace(',', ''))
            if lo <= d <= hi:
                out[side] = d
        except (InvalidOperation, TypeError, ValueError):
            pass
    return out


def normalize_cockfight_side(raw_side):
    """Map legacy MERON/WALA to COCK1/COCK2; upper-strip unknown tokens."""
    s = (raw_side or '').upper().strip()
    return COCKFIGHT_SIDE_ALIASES.get(s, s)


def cockfight_side_labels_dict(video_round):
    """
    UI labels for COCK1 / COCK2 from a CockFightRoundVideo instance (or None).
    Betting/settlement always uses COCK1 and COCK2 codes regardless.
    """
    if video_round is None:
        return {'COCK1': 'Cock 1', 'COCK2': 'Cock 2'}
    c1 = (getattr(video_round, 'label_cock1', None) or '').strip()
    c2 = (getattr(video_round, 'label_cock2', None) or '').strip()
    return {'COCK1': c1 or 'Cock 1', 'COCK2': c2 or 'Cock 2'}


def cockfight_side_display(side, labels):
    """
    Single UI string for a bet/result side code using the same labels as cockfight_side_labels_dict.
    COCK1/COCK2/DRAW (and legacy MERON/WALA via normalize_cockfight_side — caller may pass raw side).
    """
    if labels is None:
        labels = {}
    code = normalize_cockfight_side(side) if side else ''
    if code == 'DRAW':
        return 'Draw'
    if code == 'COCK1':
        return labels.get('COCK1') or 'Cock 1'
    if code == 'COCK2':
        return labels.get('COCK2') or 'Cock 2'
    return code or str(side or '')
