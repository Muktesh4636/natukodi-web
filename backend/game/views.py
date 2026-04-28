from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.urls import reverse
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from urllib.parse import urlencode
from datetime import timedelta
import os
import mimetypes
from decimal import Decimal
import redis
import json
import logging

logger = logging.getLogger('game')

from .models import (
    GameRound, Bet, DiceResult, GameSettings, RoundPrediction,
    UserSoundSetting, MegaSpinProbability, DailyRewardProbability,
    CricketBet, CockFightBet, CockFightSession,
)
from accounts.models import User, Wallet, Transaction # Added User, Wallet, Transaction for exposure API and other uses
from .serializers import (
    GameRoundSerializer, BetSerializer, CreateBetSerializer, DiceResultSerializer,
    RoundPredictionSerializer, CreatePredictionSerializer, UserSoundSettingSerializer,
    MegaSpinProbabilitySerializer, DailyRewardProbabilitySerializer
)
from .utils import (
    get_game_setting,
    get_all_game_settings,
    calculate_current_timer,
    get_redis_client,
    get_current_round_state,
    cockfight_consumer_stream_active,
    ensure_cockfight_round_video_duration,
)

# Redis connection with tiered failover
redis_client = get_redis_client()


def _build_current_round_payload_dict():
    """
    Same JSON object as GET /api/game/round/ (for embedding in prediction API and reuse).
    Returns dict or None when no round exists (matches 404 case of current_round).
    """
    cache_key = "api_cache:current_round"
    if redis_client:
        try:
            cached_response = redis_client.get(cache_key)
            if cached_response:
                return json.loads(cached_response)

            state_json = redis_client.get('current_game_state')
            if state_json:
                state = json.loads(state_json)

                now = int(timezone.now().timestamp())
                end_time = state.get('end_time', 0)
                state['timer'] = max(0, end_time - now)

                try:
                    raw_result = state.get('result') or state.get('dice_result')
                    if isinstance(raw_result, str) and raw_result:
                        state['result'] = raw_result
                    elif raw_result is not None:
                        state['result'] = str(raw_result)

                    dice_values = state.get('dice_values')
                    primary_winner = None
                    if isinstance(dice_values, list) and dice_values:
                        from collections import Counter
                        counts = Counter([int(x) for x in dice_values if x is not None])
                        winners = [(num, cnt) for num, cnt in counts.items() if cnt >= 2]
                        if winners:
                            winners.sort(key=lambda t: (-t[1], t[0]))
                            primary_winner = int(winners[0][0])
                    if primary_winner is None and isinstance(raw_result, str):
                        first = raw_result.split(',', 1)[0].strip()
                        if first.isdigit():
                            primary_winner = int(first)
                    if primary_winner is not None:
                        state['dice_result'] = primary_winner
                except Exception:
                    pass

                redis_client.set(cache_key, json.dumps(state), px=200)
                return state
        except Exception as e:
            logger.error(f"Redis error in _build_current_round_payload_dict: {e}")

    round_obj = GameRound.objects.order_by('-start_time').first()
    if not round_obj:
        return None

    round_end_time = get_game_setting('ROUND_END_TIME', 80)
    end_timestamp = int(round_obj.start_time.timestamp() + round_end_time)
    remaining_timer = max(0, int(end_timestamp - timezone.now().timestamp()))

    return {
        'round_id': round_obj.round_id,
        'status': round_obj.status,
        'end_time': end_timestamp,
        'timer': remaining_timer,
        'server_time': int(timezone.now().timestamp()),
        'is_rolling': round_obj.status == 'ROLLING',
    }


from rest_framework_simplejwt.authentication import JWTAuthentication

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def current_round(request):
    """Get current game round status from Redis (High Performance)"""
    payload = _build_current_round_payload_dict()
    if payload is None:
        return Response({'status': 'WAITING', 'message': 'No rounds found'}, status=404)
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def round_start_time(request):
    """Return current game round started time with millisecond precision.
    Response: round_id, start_time_ms (Unix ms), start_time_iso (ISO 8601 with ms).
    """
    start_dt = None
    round_id = None

    if redis_client:
        try:
            state_json = redis_client.get('current_game_state')
            if state_json:
                state = json.loads(state_json)
                round_id = state.get('round_id')
                start_str = state.get('start_time')
                if start_str and round_id:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    if timezone.is_naive(start_dt):
                        start_dt = timezone.make_aware(start_dt)
        except Exception as e:
            logger.debug(f"round_start_time Redis: {e}")

    if start_dt is None:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if round_obj:
            round_id = round_obj.round_id
            start_dt = round_obj.start_time

    if not start_dt or not round_id:
        return Response(
            {'detail': 'No active round.', 'round_id': None, 'start_time_ms': None, 'start_time_iso': None},
            status=status.HTTP_404_NOT_FOUND
        )

    # Unix timestamp in milliseconds (for client timer sync)
    start_time_ms = int(start_dt.timestamp() * 1000)
    start_time_iso = start_dt.isoformat(timespec='milliseconds') if start_dt.tzinfo else start_dt.strftime('%Y-%m-%dT%H:%M:%S.') + f'{start_dt.microsecond:06d}'[:7].rstrip('0')

    return Response({
        'round_id': round_id,
        'start_time_ms': start_time_ms,
        'start_time_iso': start_time_iso,
    })


# Redis Lua Script for Atomic Bet Placement
# Keys: [user_balance_key, total_exposure_key, user_exposure_key, bet_count_key, total_amount_key, total_bets_key]
# Args: [bet_amount, user_id, ttl_seconds]
PLACE_BET_LUA = """
local balance = tonumber(redis.call('GET', KEYS[1]) or "0")
local amount = tonumber(ARGV[1])
local user_id = ARGV[2]
local ttl = tonumber(ARGV[3]) or 3600

if amount <= 0 then
    return {false, "Invalid bet amount"}
end

-- CRITICAL: Check balance BEFORE deduction
if balance < amount then
    return {false, "Insufficient balance"}
end

-- 1. Deduct from user balance atomically
local new_balance = tonumber(redis.call('INCRBYFLOAT', KEYS[1], -amount))

-- CRITICAL: Double-check balance didn't go negative (safety check)
if new_balance < 0 then
    -- Rollback: Add the amount back
    redis.call('INCRBYFLOAT', KEYS[1], amount)
    return {false, "Insufficient balance (race condition detected)"}
end

-- 2. Increase total round exposure (initialize if doesn't exist)
local exposure_exists = redis.call('EXISTS', KEYS[2])
redis.call('INCRBYFLOAT', KEYS[2], amount)
if exposure_exists == 0 then
    redis.call('EXPIRE', KEYS[2], ttl)
end

-- 3. Increase user-specific exposure in the Hash (initialize if doesn't exist)
local hash_exists = redis.call('EXISTS', KEYS[3])
redis.call('HINCRBYFLOAT', KEYS[3], user_id, amount)
if hash_exists == 0 then
    redis.call('EXPIRE', KEYS[3], ttl)
end

-- 4. Increment total bet count (initialize if doesn't exist)
local count_exists = redis.call('EXISTS', KEYS[4])
redis.call('INCR', KEYS[4])
if count_exists == 0 then
    redis.call('EXPIRE', KEYS[4], ttl)
end

-- 5. Update round total amount (legacy key)
redis.call('INCRBYFLOAT', KEYS[5], amount)

-- 6. Update round total bets (legacy key)
redis.call('INCR', KEYS[6])

return {true, tostring(new_balance)}
"""

# Atomic: place bet + queue bet stream + track user stack (single Redis round-trip)
# Keys:
#  1 user_balance_key
#  2 round_total_exposure_key
#  3 round_user_exposure_hash_key
#  4 round_bet_count_key
#  5 round_total_amount_key (legacy)
#  6 round_total_bets_key (legacy)
#  7 bet_stream_key
#  8 user_bets_stack_key
# Args:
#  1 bet_amount
#  2 user_id
#  3 ttl_seconds
#  4 round_id
#  5 number
#  6 username
#  7 timestamp_iso
PLACE_BET_AND_QUEUE_LUA = """
local balance = tonumber(redis.call('GET', KEYS[1]) or "0")
local amount = tonumber(ARGV[1])
local user_id = ARGV[2]
local ttl = tonumber(ARGV[3]) or 3600
local round_id = ARGV[4]
local number = ARGV[5]
local username = ARGV[6]
local ts = ARGV[7]

if amount <= 0 then
    return {false, "Invalid bet amount"}
end

if balance < amount then
    return {false, "Insufficient balance"}
end

-- 1) Deduct balance
local new_balance = tonumber(redis.call('INCRBYFLOAT', KEYS[1], -amount))
if new_balance < 0 then
    redis.call('INCRBYFLOAT', KEYS[1], amount)
    return {false, "Insufficient balance (race condition detected)"}
end
redis.call('EXPIRE', KEYS[1], ttl)

-- 2) Exposure / counters
if redis.call('EXISTS', KEYS[2]) == 0 then
    redis.call('INCRBYFLOAT', KEYS[2], amount)
    redis.call('EXPIRE', KEYS[2], ttl)
else
    redis.call('INCRBYFLOAT', KEYS[2], amount)
end

if redis.call('EXISTS', KEYS[3]) == 0 then
    redis.call('HINCRBYFLOAT', KEYS[3], user_id, amount)
    redis.call('EXPIRE', KEYS[3], ttl)
else
    redis.call('HINCRBYFLOAT', KEYS[3], user_id, amount)
end

if redis.call('EXISTS', KEYS[4]) == 0 then
    redis.call('INCR', KEYS[4])
    redis.call('EXPIRE', KEYS[4], ttl)
else
    redis.call('INCR', KEYS[4])
end

-- 3) Legacy totals (also give TTL to avoid unbounded growth)
local legacy_amount
if redis.call('EXISTS', KEYS[5]) == 0 then
    legacy_amount = tonumber(redis.call('INCRBYFLOAT', KEYS[5], amount))
    redis.call('EXPIRE', KEYS[5], ttl)
else
    legacy_amount = tonumber(redis.call('INCRBYFLOAT', KEYS[5], amount))
end

local legacy_bets
if redis.call('EXISTS', KEYS[6]) == 0 then
    legacy_bets = tonumber(redis.call('INCR', KEYS[6]))
    redis.call('EXPIRE', KEYS[6], ttl)
else
    legacy_bets = tonumber(redis.call('INCR', KEYS[6]))
end

-- 4) Track per-number bets and users for smart dice engine
local nb_key = 'round:' .. tostring(round_id) .. ':number_bets'
local nu_key = 'round:' .. tostring(round_id) .. ':number:' .. tostring(number) .. ':users'
redis.call('HINCRBYFLOAT', nb_key, tostring(number), amount)
redis.call('EXPIRE', nb_key, ttl)
redis.call('SADD', nu_key, tostring(user_id))
redis.call('EXPIRE', nu_key, ttl)

-- 5) Queue to Redis Stream (trim)
local msg_id = redis.call(
    'XADD', KEYS[7],
    'MAXLEN', '~', 10000,
    '*',
    'type', 'place_bet',
    'user_id', tostring(user_id),
    'username', tostring(username),
    'round_id', tostring(round_id),
    'number', tostring(number),
    'chip_amount', tostring(amount),
    'timestamp', tostring(ts)
)

-- 5) Track bet details in Redis stack for removal
local bet_json = '{"msg_id":"' .. tostring(msg_id) .. '","round_id":"' .. tostring(round_id) .. '","number":' .. tostring(number) .. ',"chip_amount":' .. tostring(amount) .. '}'
redis.call('LPUSH', KEYS[8], bet_json)
redis.call('EXPIRE', KEYS[8], ttl)

return {true, tostring(new_balance), tostring(msg_id), tostring(legacy_bets), tostring(legacy_amount)}
"""

# Register scripts for faster evalsha when Redis is available
try:
    _place_bet_and_queue_script = redis_client.register_script(PLACE_BET_AND_QUEUE_LUA) if redis_client else None
except Exception:
    _place_bet_and_queue_script = None

# Redis Lua Script for Atomic Bet Refund
# Keys: [user_balance_key, total_exposure_key, user_exposure_key, bet_count_key, total_amount_key, total_bets_key]
# Args: [refund_amount, user_id]
REFUND_BET_LUA = """
local amount = tonumber(ARGV[1])
local user_id = ARGV[2]

-- 0. Defensive Check: Ensure exposure exists and is sufficient
local user_exp_raw = redis.call('HGET', KEYS[3], user_id)
if not user_exp_raw or tonumber(user_exp_raw) < amount then
    return {false, "NO_EXPOSURE"}
end

-- 1. Refund user balance atomically
local new_balance = tonumber(redis.call('INCRBYFLOAT', KEYS[1], amount))

-- 2. Decrease total round exposure
local total_exp = tonumber(redis.call('INCRBYFLOAT', KEYS[2], -amount))
if total_exp < 0 then redis.call('SET', KEYS[2], 0) end

-- 3. Decrease user-specific exposure in Hash
local user_exp = tonumber(redis.call('HINCRBYFLOAT', KEYS[3], user_id, -amount))
if user_exp < 0 then redis.call('HSET', KEYS[3], user_id, 0) end

-- 4. Decrement total bet count
local bet_count = tonumber(redis.call('DECR', KEYS[4]))
if bet_count < 0 then redis.call('SET', KEYS[4], 0) end

-- 5. Update round total amount (legacy key)
local legacy_amount = tonumber(redis.call('INCRBYFLOAT', KEYS[5], -amount))
if legacy_amount < 0 then redis.call('SET', KEYS[5], 0) end

-- 6. Update round total bets (legacy key)
local legacy_bets = tonumber(redis.call('DECR', KEYS[6]))
if legacy_bets < 0 then redis.call('SET', KEYS[6], 0) end

return {true, tostring(new_balance)}
"""

# Redis Lua Script: Remove most recent bet on a specific number (Redis-first)
# Uses the per-user bet stack populated by PLACE_BET_AND_QUEUE_LUA (stores JSON per bet).
# Keys:
#  1 user_balance_key
#  2 round_total_exposure_key
#  3 round_user_exposure_hash_key
#  4 round_bet_count_key
#  5 legacy_round_total_amount_key
#  6 legacy_round_total_bets_key
#  7 bet_stream_key
#  8 user_bets_stack_key
#  9 round_number_bets_hash_key  (round:<round_id>:number_bets)
# Args:
#  1 target_number
#  2 user_id
#  3 round_id
#  4 timestamp_iso
REMOVE_BET_BY_NUMBER_LUA = r"""
local target_number = tostring(ARGV[1])
local user_id = tostring(ARGV[2])
local round_id = tostring(ARGV[3])
local ts = tostring(ARGV[4])

-- Scan user's bet stack for the most recent bet on this number in the current round.
-- Stack items are JSON strings like:
-- {"msg_id":"...","round_id":"R...","number":3,"chip_amount":50}
local items = redis.call('LRANGE', KEYS[8], 0, -1)
local bet_json = nil
for i=1,#items do
  local s = items[i]
  if s and string.find(s, '\"round_id\":\"' .. round_id .. '\"', 1, true) then
    -- Match "number":<n> (no quotes)
    if string.find(s, '\"number\":' .. target_number, 1, true) then
      bet_json = s
      break
    end
  end
end

if not bet_json then
  return {false, "NO_BET"}
end

local msg_id = string.match(bet_json, '\"msg_id\":\"([^\"]+)\"')
local amount_str = string.match(bet_json, '\"chip_amount\":([0-9%.]+)')
local amount = tonumber(amount_str)
if (not msg_id) or (not amount) or (amount <= 0) then
  return {false, "INVALID_BET"}
end

-- Defensive: ensure exposure exists and is sufficient
local user_exp_raw = redis.call('HGET', KEYS[3], user_id)
if (not user_exp_raw) or (tonumber(user_exp_raw) < amount) then
  return {false, "NO_EXPOSURE"}
end

-- 1) Refund user balance atomically
local new_balance = tonumber(redis.call('INCRBYFLOAT', KEYS[1], amount))
redis.call('EXPIRE', KEYS[1], 86400)

-- 2) Decrease total round exposure
local total_exp = tonumber(redis.call('INCRBYFLOAT', KEYS[2], -amount))
if total_exp < 0 then redis.call('SET', KEYS[2], 0) end

-- 3) Decrease user exposure
local user_exp = tonumber(redis.call('HINCRBYFLOAT', KEYS[3], user_id, -amount))
if user_exp < 0 then redis.call('HSET', KEYS[3], user_id, 0) end

-- 4) Decrement bet count
local bet_count = tonumber(redis.call('DECR', KEYS[4]))
if bet_count < 0 then redis.call('SET', KEYS[4], 0) end

-- 5) Update legacy totals
local legacy_amount = tonumber(redis.call('INCRBYFLOAT', KEYS[5], -amount))
if legacy_amount < 0 then redis.call('SET', KEYS[5], 0) end

local legacy_bets = tonumber(redis.call('DECR', KEYS[6]))
if legacy_bets < 0 then redis.call('SET', KEYS[6], 0) end

-- 6) Update per-number bets hash (best-effort, keep >=0)
if KEYS[9] and string.len(KEYS[9]) > 0 then
  local nb = tonumber(redis.call('HINCRBYFLOAT', KEYS[9], target_number, -amount))
  if nb and nb < 0 then redis.call('HSET', KEYS[9], target_number, 0) end
end

-- 7) Remove the bet JSON from stack (first occurrence)
redis.call('LREM', KEYS[8], 1, bet_json)

-- 8) Queue removal event so DB worker deletes the bet row and refunds DB wallet/turnover
redis.call(
  'XADD', KEYS[7],
  'MAXLEN', '~', 10000,
  '*',
  'type', 'remove_bet',
  'msg_id', tostring(msg_id),
  'user_id', tostring(user_id),
  'round_id', tostring(round_id),
  'number', tostring(target_number),
  'refund_amount', tostring(amount),
  'timestamp', tostring(ts)
)

return {true, tostring(new_balance), tostring(msg_id), tostring(amount), tostring(legacy_bets), tostring(legacy_amount)}
"""

try:
    _remove_bet_by_number_script = redis_client.register_script(REMOVE_BET_BY_NUMBER_LUA) if redis_client else None
except Exception:
    _remove_bet_by_number_script = None

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def place_bet(request):
    """Place a bet on a number using Redis-First logic for high performance"""
    # Admins/Staff are not allowed to participate in the game
    if request.user.is_staff or request.user.is_superuser:
        return Response({'error': 'Admins are not allowed to participate in the game.'}, status=status.HTTP_403_FORBIDDEN)

    serializer = CreateBetSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    number = serializer.validated_data['number']
    chip_amount = float(serializer.validated_data['chip_amount'])
    
    # Check max bet limit
    max_bet_limit = float(get_game_setting('MAX_BET', 50000))
    if chip_amount > max_bet_limit:
        return Response({'error': f'Maximum bet amount is {max_bet_limit}'}, status=status.HTTP_400_BAD_REQUEST)

    if chip_amount <= 0:
        return Response({'error': 'Invalid bet amount'}, status=status.HTTP_400_BAD_REQUEST)
    user_id = request.user.id
    username = request.user.username
    balance_key = f"user_balance:{user_id}"
    current_redis_balance = None

    def _rstr(x):
        if x is None:
            return None
        if isinstance(x, bytes):
            try:
                return x.decode()
            except Exception:
                return None
        return str(x)

    # 1. Get current round state (Prefer Redis)
    round_id = None
    status_val = "WAITING"
    if redis_client:
        try:
            # Single network round-trip for hot keys
            pipe = redis_client.pipeline()
            pipe.get('current_round_id')
            pipe.get('current_status')
            pipe.get('current_end_time')
            pipe.get(balance_key)
            round_id_raw, status_raw, end_time_raw, current_redis_balance = pipe.execute()
            # Fallback to engine state if legacy hot keys are missing (game_engine_v3 publishes current_game_state)
            if (not round_id_raw) or (not status_raw):
                try:
                    state_json = redis_client.get('current_game_state')
                    if state_json:
                        state = json.loads(state_json)
                        round_id_raw = state.get('round_id') or round_id_raw
                        status_raw = state.get('status') or status_raw
                        if not end_time_raw:
                            try:
                                round_end = int(state.get('ROUND_END_TIME') or state.get('round_end_time') or 0)
                                timer = int(state.get('timer') or 0)
                                end_time_raw = str(int(timezone.now().timestamp()) + max(0, round_end - timer))
                            except Exception:
                                pass
                except Exception:
                    pass

            if round_id_raw and status_raw:
                round_id = _rstr(round_id_raw)
                status_val = _rstr(status_raw)
                status_val = (status_val or "WAITING").upper()
                end_time = int(end_time_raw or 0)
            else:
                # Strict Redis-only mode: do not hit DB in hot path.
                return Response(
                    {'error': 'Game state is syncing. Please retry in a moment.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        except Exception as e:
            logger.error(f"Redis error fetching round for user {user_id}: {e}")
            return Response(
                {'error': 'Betting service temporarily unavailable. Please retry.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
    else:
        return Response(
            {'error': 'Betting service temporarily unavailable. Please retry.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    # 3. Redis-First Atomic Placement (Lua Script)
    if redis_client:
        try:
            if current_redis_balance is None:
                # Keep place_bet DB-free: warm balance only from Redis session cache.
                session_json = redis_client.get(f"user_session:{user_id}")
                if session_json:
                    try:
                        session_data = json.loads(session_json)
                        session_balance = session_data.get('wallet_balance')
                        if session_balance is not None:
                            redis_client.set(balance_key, str(session_balance), ex=86400)
                            current_redis_balance = session_balance
                    except Exception:
                        pass
                if current_redis_balance is None:
                    return Response(
                        {'error': 'Balance cache is syncing. Open wallet once and retry.'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE
                    )

            keys = [
                balance_key,
                f"round:{round_id}:total_exposure",
                f"round:{round_id}:user_exposure",
                f"round:{round_id}:bet_count",
                f"round_total_amount:{round_id}", # Legacy key for compatibility
                f"round_total_bets:{round_id}",   # Legacy key for compatibility
                "bet_stream",
                f"user_bets_stack:{user_id}",
            ]
            ts = timezone.now().isoformat()

            # One Redis call: deduct + update totals + enqueue + stack push
            if _place_bet_and_queue_script:
                result = _place_bet_and_queue_script(
                    keys=keys,
                    args=[chip_amount, user_id, 3600, round_id, number, username, ts],
                )
            else:
                result = redis_client.eval(
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

            success = result[0]
            response_val = result[1]

            if not success:
                return Response({'error': response_val}, status=status.HTTP_400_BAD_REQUEST)

            new_balance = response_val

            _pay_raw = getattr(settings, 'GAME_SETTINGS', {}).get('PAYOUT_RATIOS') or {}
            payout_ratios = {str(k): float(v) for k, v in _pay_raw.items()}

            return Response({
                'message': 'Bet placed successfully',
                'wallet_balance': "{:.2f}".format(float(new_balance)),
                'round_id': round_id,
                'number': number,
                'chip_amount': "{:.2f}".format(chip_amount),
                'max_bet': max_bet_limit,
                'payout_ratios': payout_ratios,
                'settlement_note': (
                    'Returns use dice frequency when a face appears ≥2 times: stake × (1 + frequency). '
                    'payout_ratios are UI hints only.'
                ),
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Redis-only betting failed: {e}")
            return Response(
                {'error': 'Betting service temporarily unavailable. Please retry.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def remove_bet(request, number):
    """Remove a bet for a specific number"""
    user_id = request.user.id
    username = request.user.username

    # Fast Redis-first path (no DB)
    if redis_client:
        try:
            # Determine current round + status from hot keys; fallback to engine state
            pipe = redis_client.pipeline()
            pipe.get('current_round_id')
            pipe.get('current_status')
            round_id_raw, status_raw = pipe.execute()
            round_id = round_id_raw.decode() if isinstance(round_id_raw, bytes) else (str(round_id_raw) if round_id_raw else None)
            status_val = status_raw.decode() if isinstance(status_raw, bytes) else (str(status_raw) if status_raw else None)

            if not round_id or not status_val:
                state_json = redis_client.get('current_game_state')
                if state_json:
                    state = json.loads(state_json)
                    round_id = state.get('round_id') or round_id
                    status_val = state.get('status') or status_val

            status_val = (status_val or "WAITING").upper()

            stack_key = f"user_bets_stack:{user_id}"
            keys = [
                f"user_balance:{user_id}",
                f"round:{round_id}:total_exposure",
                f"round:{round_id}:user_exposure",
                f"round:{round_id}:bet_count",
                f"round_total_amount:{round_id}",
                f"round_total_bets:{round_id}",
                "bet_stream",
                stack_key,
                f"round:{round_id}:number_bets",
            ]
            ts = timezone.now().isoformat()
            if _remove_bet_by_number_script:
                result = _remove_bet_by_number_script(keys=keys, args=[int(number), user_id, round_id, ts])
            else:
                result = redis_client.eval(REMOVE_BET_BY_NUMBER_LUA, 9, *keys, int(number), user_id, round_id, ts)

            success = bool(result[0])
            if not success:
                err = result[1]
                if err == "NO_BET":
                    return Response({'error': 'Bet not found'}, status=status.HTTP_404_NOT_FOUND)
                if err == "NO_EXPOSURE":
                    return Response({'error': 'Cannot remove bet: exposure already cleared or round changed'}, status=status.HTTP_400_BAD_REQUEST)
                return Response({'error': str(err)}, status=status.HTTP_400_BAD_REQUEST)

            new_balance = result[1]
            refund_amount = result[3]

            return Response({
                'message': f'Bet on number {number} removed',
                'refund_amount': "{:.2f}".format(float(refund_amount)),
                'wallet_balance': "{:.2f}".format(float(new_balance)),
                'round_id': round_id,
            })
        except Exception as e:
            logger.exception(f"Redis-first remove_bet failed for user {username}: {e}")
            return Response({'error': 'Bet removal temporarily unavailable. Please retry.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Fallback to old DB behavior if Redis unavailable
    return Response({'error': 'Bet removal service unavailable. Please retry.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def remove_bet_by_id(request, bet_id):
    """Remove a specific bet by its ID"""
    logger.info(f"Remove bet by ID request by user {request.user.username} (ID: {request.user.id}) for bet ID {bet_id}")
    
    # 1. Get current round state (Prefer Redis)
    round_id = None
    status_val = "WAITING"
    if redis_client:
        try:
            state_json = redis_client.get('current_game_state')
            if state_json:
                state = json.loads(state_json)
                round_id = state.get('round_id')
                status_val = state.get('status')
                
                if status_val is not None:
                    status_val = status_val.upper()
        except Exception as e:
            logger.error(f"Redis error in remove_bet_by_id: {e}")
    
    # 2. Get the bet
    try:
        bet = Bet.objects.get(id=bet_id, user=request.user)
        round_obj = bet.round
    except Bet.DoesNotExist:
        return Response({'error': 'Bet not found'}, status=status.HTTP_404_NOT_FOUND)

    # Store bet amount before deleting
    refund_amount = bet.chip_amount
    bet_number = bet.number

    try:
        with transaction.atomic():
            # Refund the bet amount
            wallet = request.user.wallet
            balance_before = wallet.balance
            wallet.add(refund_amount)
            balance_after = wallet.balance

            # Update round stats in Redis
            if redis_client:
                try:
                    keys = [
                        f"user_balance:{request.user.id}",
                        f"round:{round_obj.round_id}:total_exposure",
                        f"round:{round_obj.round_id}:user_exposure",
                        f"round:{round_obj.round_id}:bet_count",
                        f"round_total_amount:{round_obj.round_id}",
                        f"round_total_bets:{round_obj.round_id}"
                    ]
                    # Execute Lua script for atomic refund
                    result = redis_client.eval(REFUND_BET_LUA, 6, *keys, float(refund_amount), request.user.id)
                    success, response_val = result[0], result[1]
                    
                    if success:
                        new_redis_balance = response_val
                    
                    # Update local object for response based on Redis values
                    round_obj.total_bets = int(redis_client.get(f"round_total_bets:{round_obj.round_id}") or 0)
                    round_obj.total_amount = Decimal(str(redis_client.get(f"round_total_amount:{round_obj.round_id}") or 0))
                except Exception as redis_err:
                    logger.error(f"Redis error updating round stats or balance: {redis_err}")
                    round_obj.total_bets = max(0, round_obj.total_bets - 1)
                    round_obj.total_amount = max(Decimal('0.00'), round_obj.total_amount - refund_amount)
                    round_obj.save()
            else:
                round_obj.total_bets = max(0, round_obj.total_bets - 1)
                round_obj.total_amount = max(Decimal('0.00'), round_obj.total_amount - refund_amount)
                round_obj.save()

            # Create refund transaction
            Transaction.objects.create(
                user=request.user,
                transaction_type='REFUND',
                amount=refund_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Refund bet ID {bet_id} on number {bet_number} in round {round_obj.round_id}"
            )

            # Delete the bet
            bet.delete()
            logger.info(f"Bet ID {bet_id} removed and refunded: User {request.user.username}, Round {round_obj.round_id}, Num {bet_number}, Amount {refund_amount}")
    except Exception as e:
        logger.exception(f"Unexpected error removing bet ID {bet_id} for user {request.user.username}: {e}")
        return Response({'error': 'Internal server error during refund'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'message': f'Bet removed',
        'refund_amount': str(refund_amount),
        'wallet_balance': str(wallet.balance),
        'round_id': round_obj.round_id,
    })


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def remove_last_bet(request):
    """Remove user's last bet using Redis-First logic"""
    user_id = request.user.id
    
    # 1. Get current round state (Prefer Redis)
    round_id = None
    status_val = "WAITING"
    if redis_client:
        try:
            pipe = redis_client.pipeline()
            pipe.get('current_round_id')
            pipe.get('current_status')
            round_id_raw, status_raw = pipe.execute()
            if round_id_raw and status_raw:
                round_id = round_id_raw
                status_val = status_raw
            else:
                state_json = redis_client.get('current_game_state')
                if state_json:
                    state = json.loads(state_json)
                    round_id = state.get('round_id')
                    status_val = state.get('status')
        except Exception as e:
            logger.error(f"Redis error fetching round: {e}")

    # 2. Redis-First Removal
    if redis_client:
        try:
            # Get last bet info from Redis Stack (LPOP)
            stack_key = f"user_bets_stack:{user_id}"
            last_bet_json = redis_client.lpop(stack_key)
            
            if not last_bet_json:
                return Response({'error': 'No bet found to remove in this round'}, status=status.HTTP_404_NOT_FOUND)
            
            last_bet = json.loads(last_bet_json)
            
            # Check if bet is from current round
            if last_bet['round_id'] != round_id:
                # CRITICAL: If round has changed, do NOT remove or refund
                # The stack might contain bets from previous rounds that are already finalized
                return Response({'error': 'Betting closed for the round in which this bet was placed'}, status=status.HTTP_400_BAD_REQUEST)
            
            # If it's a GET request, just return the bet details (but we popped it, so we must push it back)
            if request.method == 'GET':
                redis_client.lpush(stack_key, last_bet_json)
                return Response({
                    'bet': {
                        'number': last_bet['number'],
                        'chip_amount': "{:.2f}".format(float(last_bet['chip_amount']))
                    },
                    'round': {
                        'round_id': round_id,
                        'status': status_val
                    }
                })

            # If it's a DELETE request, proceed with removal
            refund_amount = float(last_bet['chip_amount'])
            bet_number = last_bet['number']
            msg_id = last_bet['msg_id']

            # Atomic Redis Refund
            keys = [
                f"user_balance:{user_id}",
                f"round:{round_id}:total_exposure",
                f"round:{round_id}:user_exposure",
                f"round:{round_id}:bet_count",
                f"round_total_amount:{round_id}",
                f"round_total_bets:{round_id}"
            ]
            result = redis_client.eval(REFUND_BET_LUA, 6, *keys, refund_amount, user_id)
            success, response_val = result[0], result[1]
            
            if not success:
                # If refund failed because of missing exposure (round transition), log it and return specific error
                if response_val == "NO_EXPOSURE":
                    logger.warning(f"Bet removal failed: NO_EXPOSURE for user {user_id} in round {round_id}. The round likely transitioned.")
                    return Response({'error': 'Cannot remove bet: Round has already transitioned or exposure cleared'}, status=status.HTTP_400_BAD_REQUEST)
                
                # If refund failed for other reasons, push the bet back to the stack
                redis_client.lpush(stack_key, last_bet_json)
                return Response({'error': response_val}, status=status.HTTP_400_BAD_REQUEST)

            # Queue the removal for DB worker
            remove_data = {
                'type': 'remove_bet',
                'msg_id': msg_id, # The ID of the place_bet message to ignore/delete
                'user_id': str(user_id),
                'round_id': round_id,
                'number': str(bet_number),
                'refund_amount': str(refund_amount),
                'timestamp': timezone.now().isoformat()
            }
            redis_client.xadd('bet_stream', remove_data, maxlen=10000)

            return Response({
                'message': f'Last bet on number {bet_number} removed',
                'refund_amount': "{:.2f}".format(refund_amount),
                'bet_number': bet_number,
                'wallet_balance': "{:.2f}".format(float(response_val)),
                'round_id': round_id,
            })

        except Exception as e:
            logger.error(f"Redis-First removal failed: {e}")
            return Response({'error': 'Internal server error during removal'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({'error': 'Redis unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_bets(request):
    """Get user's bets for current round"""
    logger.info(f"User {request.user.username} fetching their bets for the current round")
    # Get current round
    round_obj = None
    if redis_client:
        try:
            round_data = redis_client.get('current_round')
            if round_data:
                round_data = json.loads(round_data)
                
                # Check for staleness even if in Redis
                is_stale = False
                if 'start_time' in round_data:
                    from django.utils import timezone
                    from datetime import datetime
                    try:
                        start_time = datetime.fromisoformat(round_data['start_time'])
                        # Ensure timezone awareness if needed
                        if timezone.is_aware(timezone.now()) and not timezone.is_aware(start_time):
                            start_time = timezone.make_aware(start_time)
                        
                        elapsed = (timezone.now() - start_time).total_seconds()
                        round_end_time = get_game_setting('ROUND_END_TIME', 80)
                        if elapsed > round_end_time + 10:  # 10s buffer
                            is_stale = True
                    except (ValueError, TypeError):
                        pass
                
                if not is_stale:
                    try:
                        round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                    except GameRound.DoesNotExist:
                        pass
                else:
                    # Clear stale Redis data
                    redis_client.delete('current_round')
                    redis_client.delete('round_timer')
        except Exception:
            pass
    
    # Fallback to latest round
    if not round_obj:
        round_obj = GameRound.objects.order_by('-start_time').first()
    
    if round_obj:
        bets = Bet.objects.filter(user=request.user, round=round_obj)
        serializer = BetSerializer(bets, many=True)
        return Response(serializer.data)
    
    return Response([])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def user_bets_summary(request):
    """
    Get authenticated user's bets by number. round_id updates automatically to current round on each call.
    """
    round_id_param = request.query_params.get('round_id')
    round_obj = None

    if round_id_param:
        try:
            round_obj = GameRound.objects.get(round_id=round_id_param)
        except GameRound.DoesNotExist:
            return Response({'error': 'Round not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        # Current round: try Redis first
        if redis_client:
            try:
                round_data = redis_client.get('current_round')
                if round_data:
                    round_data = json.loads(round_data)
                    try:
                        round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                    except GameRound.DoesNotExist:
                        pass
            except Exception:
                pass
        if not round_obj:
            round_obj = GameRound.objects.order_by('-start_time').first()

    if not round_obj:
        return Response({
            'round_id': None,
            'bets_by_number': [{'number': n, 'amount': 0} for n in range(1, 7)]
        })

    user_bets = Bet.objects.filter(user=request.user, round=round_obj)

    bets_by_number = []
    for number in range(1, 7):
        amount = user_bets.filter(number=number).aggregate(s=Sum('chip_amount'))['s'] or 0
        bets_by_number.append({
            'number': number,
            'amount': float(amount)
        })

    return Response({
        'round_id': round_obj.round_id,
        'bets_by_number': bets_by_number
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def betting_history(request):
    """Get user's betting history (all bets, not just current round)"""
    limit = int(request.query_params.get('limit', 50))
    logger.info(f"User {request.user.username} fetching betting history (limit: {limit})")
    
    bets = Bet.objects.filter(user=request.user).select_related('round').order_by('-created_at')[:limit]
    from .serializers import BettingHistorySerializer
    serializer = BettingHistorySerializer(bets, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def round_results(request, round_id=None):
    """
    User's round results API with specific format.
    Shows user's bets, win/loss status, and wallet balance for a given round.
    """
    # Get round by ID or use latest completed round
    if round_id:
        try:
            round_obj = GameRound.objects.get(round_id=round_id)
        except GameRound.DoesNotExist:
            return Response({'error': 'Round not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        # Get the most recently COMPLETED round with dice results
        # Only show rounds that are in 'RESULT' or 'COMPLETED' status and have a result.
        # We also check if the result_time has passed to ensure we only show results after dice_result time.
        now = timezone.now()
        round_obj = GameRound.objects.filter(
            status__in=['RESULT', 'COMPLETED'],
            dice_result__isnull=False
        ).filter(
            Q(status='COMPLETED') | 
            Q(status='RESULT', result_time__lte=now) |
            Q(status='RESULT', result_time__isnull=True, start_time__lte=now - timedelta(seconds=int(get_game_setting('DICE_RESULT_TIME', 51))))
        ).order_by('-end_time', '-start_time').first()
        
        if not round_obj:
            return Response({'error': 'No completed round found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get user's bets for this round
    user_bets = Bet.objects.filter(user=request.user, round=round_obj).order_by('created_at')
    
    bets_data = []
    total_bet_amount = Decimal('0.00')
    total_payout = Decimal('0.00')
    winning_bets_count = 0
    losing_bets_count = 0

    for bet in user_bets:
        total_bet_amount += bet.chip_amount
        payout = bet.payout_amount or Decimal('0.00')
        total_payout += payout
        
        if bet.is_winner:
            winning_bets_count += 1
        else:
            losing_bets_count += 1
            
        bets_data.append({
            'id': bet.id,
            'number': bet.number,
            'chip_amount': "{:.2f}".format(float(bet.chip_amount)),
            'is_winner': bet.is_winner,
            'payout_amount': "{:.2f}".format(float(payout))
        })

    net_result = total_payout - total_bet_amount
    net_result_str = "{:+.2f}".format(float(net_result))

    # Get user's current wallet balance
    wallet_balance = "0.00"
    try:
        wallet_balance = "{:.2f}".format(float(request.user.wallet.balance))
    except Exception:
        pass

    response_data = {
        "round": {
            "round_id": round_obj.round_id,
            "status": round_obj.status,
            "dice_result": round_obj.dice_result,
            "dice_1": round_obj.dice_1,
            "dice_2": round_obj.dice_2,
            "dice_3": round_obj.dice_3,
            "dice_4": round_obj.dice_4,
            "dice_5": round_obj.dice_5,
            "dice_6": round_obj.dice_6,
            "start_time": round_obj.start_time.isoformat() if round_obj.start_time else None,
            "result_time": round_obj.result_time.isoformat() if round_obj.result_time else (round_obj.end_time.isoformat() if round_obj.end_time else None)
        },
        "bets": bets_data,
        "summary": {
            "total_bets": user_bets.count(),
            "total_bet_amount": "{:.2f}".format(float(total_bet_amount)),
            "total_payout": "{:.2f}".format(float(total_payout)),
            "net_result": net_result_str,
            "winning_bets": winning_bets_count,
            "losing_bets": losing_bets_count
        },
        "wallet_balance": wallet_balance
    }

    return Response(response_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def round_results_api(request, round_id=None):
    """
    User's round results API
    """
    return Response({
        'message': 'Round results API is working',
        'round_id': round_id,
        'user': str(request.user)
    })


def mark_correct_predictions(round_obj, dice_values=None):
    """
    Mark predictions as correct based on dice results.
    A prediction is correct if the predicted number appears 2+ times in the dice results.
    """
    from collections import Counter
    
    # Get dice values from round if not provided
    if dice_values is None:
        dice_values = [
            round_obj.dice_1, round_obj.dice_2, round_obj.dice_3,
            round_obj.dice_4, round_obj.dice_5, round_obj.dice_6
        ]
        # Filter out None values
        dice_values = [d for d in dice_values if d is not None]
    
    if not dice_values or len(dice_values) != 6:
        # Cannot determine winners without dice values
        return
    
    # Count frequency of each number
    counts = Counter(dice_values)
    
    # Find all winning numbers (appearing 2+ times)
    winning_numbers = [num for num, count in counts.items() if count >= 2]
    
    if not winning_numbers:
        # No winners - mark all predictions as incorrect
        RoundPrediction.objects.filter(round=round_obj).update(is_correct=False)
        return
    
    # Mark predictions as correct if they match any winning number
    RoundPrediction.objects.filter(round=round_obj, number__in=winning_numbers).update(is_correct=True)
    RoundPrediction.objects.filter(round=round_obj).exclude(number__in=winning_numbers).update(is_correct=False)
    
    logger.info(f"Marked predictions for round {round_obj.round_id}: Winning numbers {winning_numbers}")


def calculate_payouts(round_obj, dice_result=None, dice_values=None):
    """
    Calculate payouts for all bets in the round based on dice frequency.

    Rules:
    - Any number appearing 2+ times is a winner
    - Total payout = bet + profit, where profit = bet × frequency
    - Example: Bet 500, number appears 3x → profit 1500, total 2000 (500 returned + 1500 profit)
    - No commission: Player receives 100% of the payout.

    Args:
        round_obj: GameRound instance
        dice_result: Winning number (deprecated, kept for backward compatibility)
        dice_values: List of 6 dice values [1-6, 1-6, 1-6, 1-6, 1-6, 1-6]
    """
    from collections import Counter
    
    # Get dice values from round if not provided
    if dice_values is None:
        dice_values = [
            round_obj.dice_1, round_obj.dice_2, round_obj.dice_3,
            round_obj.dice_4, round_obj.dice_5, round_obj.dice_6
        ]
        # Filter out None values
        dice_values = [d for d in dice_values if d is not None]
    
    if not dice_values or len(dice_values) != 6:
        # Check if we can parse dice_values from dice_result string
        if dice_result and isinstance(dice_result, str):
            try:
                # Parse "1, 2, 3, 4, 5, 6" into [1, 2, 3, 4, 5, 6]
                parsed_values = [int(n.strip()) for n in dice_result.split(',') if n.strip().isdigit()]
                if parsed_values:
                    dice_values = parsed_values
            except ValueError:
                pass
    
    if not dice_values:
        # Cannot determine winners without dice values
        return

    # Count frequency of each number
    counts = Counter(dice_values)
    
    # Find all winning numbers (appearing 2+ times)
    winning_numbers = [num for num, count in counts.items() if count >= 2]
    
    if not winning_numbers:
        # No winners if no number appears 2+ times
        return
    
    # Process each winning number
    for winning_number in winning_numbers:
        frequency = counts[winning_number]
        # Payout: return bet + profit. Profit = bet * frequency.
        # Total = bet + (bet * frequency) = bet * (1 + frequency)
        # Example: bet 500, 3 appears 3x → profit 1500, total 2000
        payout_multiplier = Decimal(str(frequency))
        
        # Get all bets on this winning number
        winning_bets = Bet.objects.filter(round=round_obj, number=winning_number)
        
        for bet in winning_bets:
            # Safeguard: Skip if already processed to prevent duplicate payouts
            if bet.is_winner:
                continue
                
            # Calculate total payout: bet + profit = bet * (1 + frequency)
            total_payout_amount = bet.chip_amount * (1 + payout_multiplier)
            
            # Store the total payout amount in bet.payout_amount for reference
            bet.payout_amount = total_payout_amount
            bet.is_winner = True
            bet.save()

            # Add 100% to winner's wallet
            wallet = bet.user.wallet
            balance_before = wallet.balance
            
            # Use atomic F() update for settlement to match new rules
            Wallet.objects.filter(user_id=bet.user.id).update(balance=F('balance') + total_payout_amount)
            
            # Refresh to get exact balance for Redis and Logs
            wallet.refresh_from_db()
            balance_after = wallet.balance

            # Update Redis balance for winner (CRITICAL for Redis-First betting)
            if redis_client:
                try:
                    balance_key = f"user_balance:{bet.user.id}"
                    # Use set with nx=True is not appropriate here as we WANT to overwrite with the new settled balance
                    # but we should ensure we don't overwrite if Redis was already ahead (though for settlement, DB is source)
                    redis_client.set(balance_key, str(balance_after), ex=3600)
                    
                    # Store final net result in Redis for fast retrieval
                    # round:{round_id}:final_net:{user_id}
                    # We use HINCRBYFLOAT because a user might have multiple winning bets
                    net_key = f"round:{round_obj.round_id}:final_net"
                    redis_client.hincrbyfloat(net_key, str(bet.user.id), float(total_payout_amount))
                    redis_client.expire(net_key, 3600)
                except Exception as re:
                    logger.error(f"Failed to update Redis balance for winner {bet.user.id}: {re}")

            # Create transaction for winner (100%)
            Transaction.objects.create(
                user=bet.user,
                transaction_type='WIN',
                amount=total_payout_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Win on number {winning_number} (appeared {frequency}x) in round {round_obj.round_id}. Payout: {total_payout_amount} (Multiplier: {payout_multiplier}x)"
            )

    # CRITICAL: Mark all losing bets in this round
    # A losing bet is any bet in this round that is NOT a winner
    Bet.objects.filter(round=round_obj, is_winner=False).update(payout_amount=Decimal('0.00'))
    
    # Also subtract exposure from final_net in Redis to get the true net result
    if redis_client:
        try:
            exposure_key = f"round:{round_obj.round_id}:user_exposure"
            net_key = f"round:{round_obj.round_id}:final_net"
            user_exposures = redis_client.hgetall(exposure_key)
            for user_id_str, exposure_amount in user_exposures.items():
                # Subtract exposure (total bet) from payout to get net
                redis_client.hincrbyfloat(net_key, user_id_str, -float(exposure_amount))
        except Exception as e:
            logger.error(f"Error calculating final net results in Redis: {e}")
    
    logger.info(f"Payouts calculated for round {round_obj.round_id}. Winning numbers: {winning_numbers}")


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_sound_settings(request):
    """
    GET: Get current user's sound settings.
    POST: Update user's sound settings.
    """
    settings_obj, created = UserSoundSetting.objects.get_or_create(user=request.user)
    
    if request.method == 'GET':
        serializer = UserSoundSettingSerializer(settings_obj)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = UserSoundSettingSerializer(settings_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.info(f"User {request.user.username} updated sound settings: {serializer.data}")
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def admin_mega_spin_prob(request, user_id=None):
    """Admin: Get or set Mega Spin probabilities (global or user-specific)"""
    if user_id:
        user = get_object_or_404(User, id=user_id)
        prob_obj, created = MegaSpinProbability.objects.get_or_create(user=user)
    else:
        prob_obj, created = MegaSpinProbability.objects.get_or_create(user=None)
    
    if request.method == 'GET':
        serializer = MegaSpinProbabilitySerializer(prob_obj)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = MegaSpinProbabilitySerializer(prob_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def admin_daily_reward_prob(request, user_id=None):
    """Admin: Get or set Daily Reward probabilities (global or user-specific)"""
    if user_id:
        user = get_object_or_404(User, id=user_id)
        prob_obj, created = DailyRewardProbability.objects.get_or_create(user=user)
    else:
        prob_obj, created = DailyRewardProbability.objects.get_or_create(user=None)
    
    if request.method == 'GET':
        serializer = DailyRewardProbabilitySerializer(prob_obj)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = DailyRewardProbabilitySerializer(prob_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def app_version(request):
    """
    API endpoint to check for app updates.
    Returns the latest version code, version name, and download URL.
    """
    try:
        from .utils import get_game_setting
        
        # Get settings from database/Redis
        version_code = int(get_game_setting('APP_VERSION_CODE', 1))
        version_name = get_game_setting('APP_VERSION_NAME', '1.0.0')
        download_url = get_game_setting('APP_DOWNLOAD_URL', '/api/download/apk/')
        force_update = get_game_setting('APP_FORCE_UPDATE', 'false').lower() == 'true'
        
        return Response({
            'version_code': version_code,
            'version_name': version_name,
            'download_url': download_url,
            'force_update': force_update,
            'timestamp': timezone.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in app_version API: {e}")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def winning_results(request, round_id=None):
    """
    Get winning results for a specific round.
    Returns: All winning bets, statistics, and winning numbers with frequencies.
    """
    from collections import Counter
    from django.db.models import Sum
    
    logger.info(f"Winning results called with round_id: {round_id}, path: {request.path}")
    
    # Validate round_id - if it's empty, whitespace, or just a tab, treat as None
    if round_id:
        round_id = round_id.strip()
        if not round_id or len(round_id) == 0 or round_id.lower() == 'latest' or round_id.lower() == 'current':
            round_id = None
    
    # Get round by ID or use latest completed round.
    #
    # Important: The WebSocket/engine publishes results to Redis immediately, but DB persistence
    # (round_worker) can lag by a few seconds. If we always pick "latest RESULT/COMPLETED" from DB,
    # we may accidentally return the previous round during that window, which looks like "wrong dice".
    redis_state = None
    round_obj = None
    if round_id:
        try:
            round_obj = GameRound.objects.get(round_id=round_id)
        except GameRound.DoesNotExist:
            logger.warning(f"Round {round_id} not found, falling back to latest")
            round_obj = None
    
    if not round_obj:
        # Prefer the current engine state if it already has a result.
        if redis_client:
            try:
                state_json = redis_client.get('current_game_state')
                if state_json:
                    redis_state = json.loads(state_json)
                    redis_round_id = (redis_state.get('round_id') or '').strip()
                    redis_status = (redis_state.get('status') or '').strip().upper()
                    redis_result = redis_state.get('dice_result') or redis_state.get('result')
                    redis_dice_values = redis_state.get('dice_values')
                    if redis_round_id and redis_status in ('RESULT', 'COMPLETED') and redis_result and redis_dice_values:
                        round_obj = GameRound.objects.filter(round_id=redis_round_id).first()
            except Exception as re:
                logger.error(f"Redis error in winning_results (current_game_state): {re}")

        # Fallback: Get the absolute most recent round with status RESULT or COMPLETED
        if not round_obj:
            round_obj = GameRound.objects.filter(
                status__in=['RESULT', 'COMPLETED'],
                dice_result__isnull=False
            ).order_by('-id').first()
            
            # If no RESULT/COMPLETED round found, fallback to any round with a dice result
            if not round_obj:
                round_obj = GameRound.objects.filter(
                    dice_result__isnull=False
                ).order_by('-id').first()
        
        if not round_obj:
            return Response({
                'error': 'No completed round results found',
                'message': 'No completed rounds with dice results available yet.'
            }, status=status.HTTP_404_NOT_FOUND)
    
    # Debug prints as requested
    print(f"DEBUG: winning_results API called with round_id={round_id}")
    print(f"DEBUG: Selected Round ID: {round_obj.round_id if round_obj else 'None'}")
    print(f"DEBUG: Round Status: {round_obj.status if round_obj else 'None'}")
    print(f"DEBUG: Round Dice Result: {round_obj.dice_result if round_obj else 'None'}")
    print(f"DEBUG: User: {request.user.id if request.user.is_authenticated else 'Anonymous'}")
    if round_obj:
        print(f"DEBUG: All bets for this round: {Bet.objects.filter(round=round_obj).count()}")
        if request.user.is_authenticated:
            print(f"DEBUG: User bets: {Bet.objects.filter(round=round_obj, user=request.user).count()}")
    
    # Get user's bets for this round if authenticated
    bets_data = []
    user_total_bet_amount = Decimal('0.00')
    user_total_payout = Decimal('0.00')
    user_winning_bets = 0
    user_losing_bets = 0
    wallet_balance = "0.00"

    if request.user.is_authenticated:
        # Use aggregate for more reliable totals as suggested
        user_bets_query = Bet.objects.filter(user=request.user, round=round_obj)
        
        # Calculate totals safely
        user_total_bet_amount = user_bets_query.aggregate(
            total=Sum('chip_amount')
        )['total'] or Decimal('0.00')
        
        user_total_payout = user_bets_query.aggregate(
            total=Sum('payout_amount')
        )['total'] or Decimal('0.00')
        
        # Get individual bets for the list
        user_bets = user_bets_query.order_by('created_at')
        for bet in user_bets:
            payout = bet.payout_amount or Decimal('0.00')
            if bet.is_winner:
                user_winning_bets += 1
            else:
                user_losing_bets += 1
            bets_data.append({
                'id': bet.id,
                'number': bet.number,
                'chip_amount': "{:.2f}".format(float(bet.chip_amount)),
                'is_winner': bet.is_winner,
                'payout_amount': "{:.2f}".format(float(payout))
            })
        try:
            from accounts.models import Wallet
            wallet, _ = Wallet.objects.get_or_create(user=request.user)
            wallet_balance = "{:.2f}".format(float(wallet.balance))
        except Exception:
            pass

    user_net_result = Decimal('0.00')
    if request.user.is_authenticated and redis_client:
        try:
            net_key = f"round:{round_obj.round_id}:final_net"
            redis_net = redis_client.hget(net_key, str(request.user.id))
            if redis_net is not None:
                user_net_result = Decimal(str(redis_net))
            else:
                # Fallback to DB calculation if Redis key is missing
                user_net_result = user_total_payout - user_total_bet_amount
        except Exception as e:
            logger.error(f"Error fetching net result from Redis: {e}")
            user_net_result = user_total_payout - user_total_bet_amount
    else:
        user_net_result = user_total_payout - user_total_bet_amount

    # Format net_result as integer as requested
    net_result_formatted = int(user_net_result)

    # If we didn't load redis_state earlier but Redis is available, load it now so we can
    # fill dice fields from the same source as WebSocket (prevents temporary mismatches).
    if redis_state is None and redis_client:
        try:
            state_json = redis_client.get('current_game_state')
            if state_json:
                redis_state = json.loads(state_json)
        except Exception:
            redis_state = None

    redis_round_id = (redis_state.get('round_id') or '').strip() if isinstance(redis_state, dict) else ''
    redis_result = (redis_state.get('dice_result') or redis_state.get('result')) if isinstance(redis_state, dict) else None
    redis_dice_values = redis_state.get('dice_values') if isinstance(redis_state, dict) else None
    use_redis_for_this_round = bool(round_obj and redis_round_id and round_obj.round_id == redis_round_id and redis_dice_values)

    dice_1 = round_obj.dice_1
    dice_2 = round_obj.dice_2
    dice_3 = round_obj.dice_3
    dice_4 = round_obj.dice_4
    dice_5 = round_obj.dice_5
    dice_6 = round_obj.dice_6
    dice_result_value = str(round_obj.dice_result) if round_obj.dice_result is not None else None

    if use_redis_for_this_round:
        try:
            if isinstance(redis_dice_values, list) and len(redis_dice_values) >= 6:
                dice_1, dice_2, dice_3, dice_4, dice_5, dice_6 = redis_dice_values[:6]
            if redis_result is not None:
                dice_result_value = str(redis_result)
        except Exception:
            pass

    response_data = {
        "round": {
            "round_id": round_obj.round_id,
            "status": round_obj.status,
            "dice_result": dice_result_value,
            "dice_1": dice_1,
            "dice_2": dice_2,
            "dice_3": dice_3,
            "dice_4": dice_4,
            "dice_5": dice_5,
            "dice_6": dice_6,
            "start_time": round_obj.start_time.isoformat() if round_obj.start_time else None,
            "result_time": round_obj.result_time.isoformat() if round_obj.result_time else (round_obj.end_time.isoformat() if round_obj.end_time else None)
        },
        "bets": bets_data,
        "summary": {
            "total_bets": len(bets_data),
            "total_bet_amount": "{:.2f}".format(float(user_total_bet_amount)),
            "total_payout": "{:.2f}".format(float(user_total_payout)),
            "net_result": net_result_formatted,
            "winning_bets": user_winning_bets,
            "losing_bets": user_losing_bets
        },
        "wallet_balance": wallet_balance
    }

    response = Response(response_data)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@api_view(['GET'])
@permission_classes([IsAdminUser])
def game_stats(request):
    """Admin: Get game statistics"""
    logger.info(f"Admin {request.user.username} fetching game statistics")
    # Get current round
    current_round_obj = None
    if redis_client:
        try:
            # Use current_game_state which is the primary source of truth for the engine
            state_json = redis_client.get('current_game_state')
            if state_json:
                state = json.loads(state_json)
                round_id = state.get('round_id')
                if round_id:
                    try:
                        current_round_obj = GameRound.objects.get(round_id=round_id)
                    except GameRound.DoesNotExist:
                        pass
            
            # Fallback to current_round if current_game_state is missing or round not found
            if not current_round_obj:
                round_data = redis_client.get('current_round')
                if round_data:
                    round_data = json.loads(round_data)
                    try:
                        current_round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                    except GameRound.DoesNotExist:
                        pass
        except Exception as e:
            logger.error(f"Redis error in game_stats: {e}")
    
    # Fallback to latest round
    if not current_round_obj:
        current_round_obj = GameRound.objects.order_by('-start_time').first()

    stats = {
        'current_round': GameRoundSerializer(current_round_obj).data if current_round_obj else None,
        'total_rounds': GameRound.objects.count(),
        'total_bets': Bet.objects.count(),
        'total_amount': Bet.objects.aggregate(models.Sum('chip_amount'))['chip_amount__sum'] or 0,
    }

    return Response(stats)


# NOTE: game_settings_api removed temporarily — see temporary_deleted/game_settings_api_views.py


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@csrf_exempt
def max_bet(request):
    """Get or set max bet amount. GET: returns max_bet. POST: set max_bet (admin only)."""
    from .utils import get_game_setting, clear_game_setting_cache

    if request.method == 'GET':
        max_bet_val = float(get_game_setting('MAX_BET', 50000))
        return Response({'max_bet': max_bet_val})

    elif request.method == 'POST':
        # Use JWT authentication for POST if available
        user = request.user
        if not user.is_authenticated:
            # Try to authenticate manually if needed (for manual/API calls)
            from rest_framework_simplejwt.authentication import JWTAuthentication
            try:
                auth_res = JWTAuthentication().authenticate(request)
                if auth_res:
                    user = auth_res[0]
            except Exception:
                pass

        if not user.is_authenticated or not user.is_staff:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
        
        data = request.data
        max_bet_val = data.get('max_bet') or data.get('max-bet')
        if max_bet_val is None:
            return Response({'error': 'max_bet or max-bet required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            max_bet_val = float(max_bet_val)
        except (TypeError, ValueError):
            return Response({'error': 'max_bet must be a number'}, status=status.HTTP_400_BAD_REQUEST)
        if max_bet_val < 0:
            return Response({'error': 'max_bet must be non-negative'}, status=status.HTTP_400_BAD_REQUEST)
        
        GameSettings.objects.update_or_create(
            key='MAX_BET',
            defaults={'value': str(int(max_bet_val)), 'description': 'Maximum bet amount per number'}
        )
        clear_game_setting_cache(['MAX_BET'])
        return Response({'max_bet': max_bet_val})


# NOTE: game_timer_settings removed temporarily — see temporary_deleted/game_settings_api_views.py


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def dice_frequency(request, round_id=None):
    """
    API endpoint to get the dice frequency for the last N rounds.
    Query param: count (default: 10)
    """
    try:
        from collections import Counter
        count = int(request.query_params.get('count', 10))
        count = max(1, min(count, 100))
        
        # Try to get from Redis first to reduce DB load
        cache_key = f"dice_frequency_cache_{count}"
        if redis_client:
            try:
                cached_data = redis_client.get(cache_key)
                if cached_data:
                    results_data = json.loads(cached_data)
                    # Add wallet_balance if authenticated (don't cache this part)
                    if request.user.is_authenticated:
                        try:
                            # Try to get balance from Redis cache first
                            balance = redis_client.get(f"user_balance:{request.user.id}")
                            if balance is None:
                                balance = str(request.user.wallet.balance)
                            results_data["wallet_balance"] = "{:.2f}".format(float(balance))
                        except:
                            results_data["wallet_balance"] = "0.00"
                    return Response(results_data)
            except Exception as re:
                logger.error(f"Redis frequency cache fetch error: {re}")

        # Fetch from database
        recent_rounds = GameRound.objects.filter(
            status__in=['RESULT', 'COMPLETED'],
            dice_result__isnull=False
        ).order_by('-start_time')[:count]

        results = []
        for round_obj in recent_rounds:
            dice_values = [
                round_obj.dice_1, round_obj.dice_2, round_obj.dice_3,
                round_obj.dice_4, round_obj.dice_5, round_obj.dice_6
            ]
            # Filter out None values
            dice_values = [d for d in dice_values if d is not None]
            
            # Calculate frequency
            counts = Counter(dice_values)
            
            # Winning numbers are those that appear 2+ times
            winning_numbers_data = []
            # Only include numbers with frequency >= 2
            for num in sorted(counts.keys()):
                if counts[num] >= 2:
                    winning_numbers_data.append({
                        "number": num,
                        "frequency": counts[num],
                        "payout_multiplier": float(counts[num])
                    })

            # Format dice_result as a single winning number (highest frequency)
            # If multiple winners, use the first one. If no winners, use "0"
            primary_winner = winning_numbers_data[0]["number"] if winning_numbers_data else 0
            
            # Calculate a fallback end_time if it's null (start_time + 70s)
            calculated_end_time = round_obj.end_time
            if not calculated_end_time and round_obj.start_time:
                calculated_end_time = round_obj.start_time + timedelta(seconds=70)

            results.append({
                "round_id": round_obj.round_id,
                "dice_result": primary_winner,
                "round": {
                    "round_id": round_obj.round_id,
                    "status": round_obj.status.lower(),
                    "dice_result": primary_winner,
                    "dice_values": dice_values,
                    "start_time": round_obj.start_time.isoformat() if round_obj.start_time else None,
                    "result_time": round_obj.result_time.isoformat() if round_obj.result_time else None,
                    "end_time": calculated_end_time.isoformat() if calculated_end_time else None
                },
                "winning_numbers": winning_numbers_data
            })

        if results:
            # Cache the result for 2 seconds to reduce DB load
            if redis_client:
                try:
                    redis_client.set(cache_key, json.dumps(results[0]), ex=2)
                except: pass

            # Add wallet_balance if authenticated
            if request.user.is_authenticated:
                try:
                    # Try to get balance from Redis cache first
                    balance = redis_client.get(f"user_balance:{request.user.id}")
                    if balance is None:
                        balance = str(request.user.wallet.balance)
                    results[0]["wallet_balance"] = "{:.2f}".format(float(balance))
                except:
                    results[0]["wallet_balance"] = "0.00"
            return Response(results[0])
            
        return Response({"error": "No results found"}, status=404)
    except Exception as e:
        logger.error(f"Error in dice_frequency API: {e}")
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def last_round_results(request):
    """
    API endpoint to get the last completed round results.
    Returns: round_id and all 6 dice results (dice_1 through dice_6).
    """
    try:
        logger.info("Public last round results API access")
        
        # Try to get from Redis first for maximum performance and to avoid DB timeouts
        if redis_client:
            try:
                last_results = redis_client.get('last_round_results_cache')
                if last_results:
                    logger.info("Returning last round results from Redis cache")
                    return Response(json.loads(last_results))
            except Exception as re:
                logger.error(f"Redis cache read error: {re}")

        # Fallback to DB if not in Redis or Redis fails
        # Get the last completed round (status is 'RESULT' or 'COMPLETED')
        # We order by start_time descending because end_time might be null for recent results
        last_round = GameRound.objects.filter(
            status__in=['RESULT', 'COMPLETED'],
            dice_result__isnull=False
        ).order_by('-start_time').first()
    
        if not last_round:
            logger.warning("Last round results requested but no completed rounds found")
            return Response({
                'error': 'No completed round found'
            }, status=status.HTTP_404_NOT_FOUND)
    
        # Return round_id and all 6 dice values
        result = {
            'round_id': last_round.round_id,
            'dice_1': last_round.dice_1,
            'dice_2': last_round.dice_2,
            'dice_3': last_round.dice_3,
            'dice_4': last_round.dice_4,
            'dice_5': last_round.dice_5,
            'dice_6': last_round.dice_6,
            'dice_result': last_round.dice_result,
            'timestamp': last_round.result_time.isoformat() if last_round.result_time else last_round.start_time.isoformat()
        }

        # Cache in Redis for 30 seconds to reduce DB load
        if redis_client:
            try:
                redis_client.set('last_round_results_cache', json.dumps(result), ex=30)
            except Exception as re:
                logger.error(f"Redis cache write error: {re}")

        logger.info(f"Returning last round results: {result}")
        return Response(result)
    except Exception as e:
        logger.error(f"Error in last_round_results: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def recent_round_results(request):
    """
    API endpoint to get the last N completed round results.
    Query param: count (default: 3)
    """
    try:
        count = int(request.query_params.get('count', 3))
        # Limit count to reasonable range
        count = max(1, min(count, 50))
        
        logger.info(f"Public recent {count} round results API access")
        
        # Try to get from Redis first
        cache_key = f'recent_round_results_{count}_cache'
        if redis_client:
            try:
                cached_data = redis_client.get(cache_key)
                if cached_data:
                    return Response(json.loads(cached_data))
            except Exception as re:
                logger.error(f"Redis cache read error: {re}")

        # Fetch from database
        recent_rounds = GameRound.objects.filter(
            status__in=['RESULT', 'COMPLETED'],
            dice_result__isnull=False
        ).order_by('-start_time')[:count]

        results = []
        for round_obj in recent_rounds:
            dt = round_obj.result_time or round_obj.end_time or round_obj.start_time
            if dt:
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.utc)
                ts_utc = dt.astimezone(timezone.utc)
                timestamp_str = ts_utc.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
            else:
                timestamp_str = None
            results.append({
                'round_id': round_obj.round_id,
                'dice_1': round_obj.dice_1,
                'dice_2': round_obj.dice_2,
                'dice_3': round_obj.dice_3,
                'dice_4': round_obj.dice_4,
                'dice_5': round_obj.dice_5,
                'dice_6': round_obj.dice_6,
                'dice_result': round_obj.dice_result,
                'timestamp': timestamp_str
            })

        # Cache in Redis (short TTL so new rounds appear quickly)
        if redis_client:
            try:
                redis_client.set(cache_key, json.dumps(results), ex=5)
            except Exception as re:
                logger.error(f"Redis cache write error: {re}")

        return Response(results)
    except Exception as e:
        logger.error(f"Error in recent_round_results: {e}")
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def round_bets(request, round_id=None):
    """
    Get all bets for a specific round.
    Shows how players have bet for that round.
    
    Query params:
    - round_id: (optional) Specific round ID. If not provided, uses current/latest round.
    - number: (optional) Filter bets by number (1-6)
    - user_id: (optional) Filter bets by user ID (admin only)
    - limit: (optional) Limit number of results (default: 1000)
    """
    logger.info(f"User {request.user.username} fetching bets for round {round_id or 'current'}")
    
    # Get round by ID or use current round
    if round_id:
        try:
            round_obj = GameRound.objects.get(round_id=round_id)
        except GameRound.DoesNotExist:
            logger.warning(f"Round {round_id} not found for user {request.user.username}")
            return Response({'error': 'Round not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        # Get current/latest round
        round_obj = None
        if redis_client:
            try:
                # Use current_game_state which is the primary source of truth for the engine
                state_json = redis_client.get('current_game_state')
                if state_json:
                    state = json.loads(state_json)
                    rid = state.get('round_id')
                    if rid:
                        try:
                            round_obj = GameRound.objects.get(round_id=rid)
                        except GameRound.DoesNotExist:
                            pass
                
                # Fallback to current_round if current_game_state is missing or round not found
                if not round_obj:
                    round_data = redis_client.get('current_round')
                    if round_data:
                        round_data = json.loads(round_data)
                        try:
                            round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                        except GameRound.DoesNotExist:
                            pass
            except Exception as e:
                logger.error(f"Redis error in round_bets: {e}")
        
        if not round_obj:
            round_obj = GameRound.objects.order_by('-start_time').first()
        
        if not round_obj:
            logger.warning(f"No rounds found for user {request.user.username}")
            return Response({'error': 'No round found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get query parameters
    number_filter = request.query_params.get('number')
    user_id_filter = request.query_params.get('user_id')
    limit = int(request.query_params.get('limit', 1000))
    
    # Check if user is admin
    is_admin = request.user.is_staff or request.user.is_superuser
    
    # Build query - Order by created_at (oldest first) to show betting order
    bets_query = Bet.objects.filter(round=round_obj).select_related('user').order_by('created_at')
    
    # Filter by number if provided
    if number_filter:
        try:
            number = int(number_filter)
            if 1 <= number <= 6:
                bets_query = bets_query.filter(number=number)
            else:
                return Response({'error': 'Number must be between 1 and 6'}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({'error': 'Invalid number parameter'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Filter by user_id if provided (admin only)
    if user_id_filter:
        if is_admin:
            try:
                bets_query = bets_query.filter(user_id=int(user_id_filter))
            except ValueError:
                return Response({'error': 'Invalid user_id parameter'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(
                {'error': 'Only admins can filter by user_id'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    elif not is_admin:
        # Non-admin users can only see their own bets
        bets_query = bets_query.filter(user=request.user)
    
    # Apply limit and ordering
    bets = bets_query.order_by('created_at')[:limit]
    
    # Group bets by user and number to get chip breakdown
    player_bets_breakdown = {}
    player_totals = {} # New: track total across all numbers for each player
    for bet in bets:
        user_key = bet.user.username
        if user_key not in player_bets_breakdown:
            player_bets_breakdown[user_key] = {}
        if user_key not in player_totals:
            player_totals[user_key] = Decimal('0.00')

        num_key = str(bet.number)
        if num_key not in player_bets_breakdown[user_key]:
            player_bets_breakdown[user_key][num_key] = {
                'total_amount': Decimal('0.00'),
                'chips': {},
                'last_chip_amount': bet.chip_amount,  # Track last chip amount used
                'last_bet_time': bet.created_at    # Track last bet timestamp for ordering
            }

        # Update last chip amount (keep the most recent one)
        player_bets_breakdown[user_key][num_key]['last_chip_amount'] = bet.chip_amount
        player_bets_breakdown[user_key][num_key]['last_bet_time'] = bet.created_at

        chip_val = str(int(bet.chip_amount)) if bet.chip_amount == bet.chip_amount.to_integral_value() else str(bet.chip_amount)
        player_bets_breakdown[user_key][num_key]['total_amount'] += bet.chip_amount
        player_bets_breakdown[user_key][num_key]['chips'][chip_val] = player_bets_breakdown[user_key][num_key]['chips'].get(chip_val, 0) + 1
        player_totals[user_key] += bet.chip_amount

    # Serialize bets with breakdown
    bets_data = []
    individual_bets = []  # New: individual bets with timestamps
    for user_name, numbers in player_bets_breakdown.items():
        for num, data in numbers.items():
            # Create a summary for each user per number (sort chips by value ascending)
            sorted_chips = sorted(data['chips'].items(), key=lambda x: float(x[0]))
            chip_breakdown_str = ", ".join([f"{count}x{chip}" for chip, count in sorted_chips])
            bets_data.append({
                'username': user_name,
                'number': int(num),
                'amount': str(data['total_amount']),
                'total_player_bet': str(player_totals[user_name]), # New: total across all numbers
                'chip_breakdown': dict(sorted_chips),  # Sort chip breakdown by chip value
                'chip_summary': chip_breakdown_str,
                'last_chip_amount': str(data['last_chip_amount']),  # Last chip amount used on this number
                'last_bet_time': data['last_bet_time'].isoformat()    # Timestamp of last bet
            })

    # Add individual bets with timestamps (already ordered chronologically by the query above)
    for bet in bets:
        individual_bets.append({
            'id': bet.id,
            'user_id': bet.user.id,
            'username': bet.user.username,
            'number': bet.number,
            'chip_amount': str(bet.chip_amount),
            'created_at': bet.created_at.isoformat(),
            'is_winner': bet.is_winner,
            'payout_amount': str(bet.payout_amount) if bet.payout_amount else None
        })
    
    # Calculate statistics by number
    from django.db.models import Sum, Count
    stats_by_number = []
    for num in range(1, 7):
        number_bets = Bet.objects.filter(round=round_obj, number=num)
        number_stats = number_bets.aggregate(
            total_bets=Count('id'),
            total_amount=Sum('chip_amount'),
            total_winners=Count('id', filter=Q(is_winner=True)),
            total_payout=Sum('payout_amount', filter=Q(is_winner=True))
        )
        stats_by_number.append({
            'number': num,
            'total_bets': number_stats['total_bets'] or 0,
            'total_amount': str(number_stats['total_amount'] or Decimal('0.00')),
            'total_winners': number_stats['total_winners'] or 0,
            'total_payout': str(number_stats['total_payout'] or Decimal('0.00')),
        })
    
    # Calculate overall statistics
    all_bets = Bet.objects.filter(round=round_obj)
    overall_stats = all_bets.aggregate(
        total_bets=Count('id'),
        total_amount=Sum('chip_amount'),
        total_unique_players=Count('user_id', distinct=True),
        total_winners=Count('id', filter=Q(is_winner=True)),
        total_payout=Sum('payout_amount', filter=Q(is_winner=True))
    )
    
    logger.info(f"Fetched {len(bets_data)} bets for round {round_obj.round_id}")
    
    return Response({
        'round': {
            'round_id': round_obj.round_id,
            'status': round_obj.status,
            'dice_result': round_obj.dice_result,
            'dice_1': round_obj.dice_1,
            'dice_2': round_obj.dice_2,
            'dice_3': round_obj.dice_3,
            'dice_4': round_obj.dice_4,
            'dice_5': round_obj.dice_5,
            'dice_6': round_obj.dice_6,
            'start_time': round_obj.start_time.isoformat(),
            'result_time': round_obj.result_time.isoformat() if round_obj.result_time else None,
        },
        'bets': bets_data,  # Grouped bets by user and number
        'individual_bets': individual_bets,  # Individual bets with timestamps
        'statistics': {
            'overall': {
                'total_bets': overall_stats['total_bets'] or 0,
                'total_amount': str(overall_stats['total_amount'] or Decimal('0.00')),
                'total_unique_players': overall_stats['total_unique_players'] or 0,
                'total_winners': overall_stats['total_winners'] or 0,
                'total_payout': str(overall_stats['total_payout'] or Decimal('0.00')),
            },
            'by_number': stats_by_number,
        },
        'count': len(bets_data),
        'individual_count': len(individual_bets),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def round_exposure(request, round_id=None):
    """
    High-speed Exposure API: Calculates totals entirely from Redis.
    """
    # 1. Determine Round ID
    if not round_id:
        if redis_client:
            try:
                # Fast path: legacy hot key (kept up-to-date by game_engine_v3)
                round_id = redis_client.get('current_round_id') or round_id

                # Use current_game_state which is the primary source of truth for the engine
                state_json = redis_client.get('current_game_state')
                if state_json:
                    state = json.loads(state_json)
                    round_id = state.get('round_id')
                
                # Fallback to current_round if current_game_state is missing
                if not round_id:
                    round_data = redis_client.get('current_round')
                    if round_data:
                        round_id = json.loads(round_data).get('round_id')
            except: pass
        
        if not round_id:
            round_obj = GameRound.objects.order_by('-start_time').first()
            if not round_obj:
                return Response({'error': 'No round found'}, status=404)
            round_id = round_obj.round_id

    # 2. Check for 200ms cached response
    # Cache key is specific to the round and the user (or admin)
    user_id = request.user.id
    is_admin = request.user.is_staff or request.user.is_superuser
    target_player_id = request.query_params.get('player_id')
    
    cache_key = f"api_cache:exposure:{round_id}:{user_id}"
    if is_admin:
        cache_key += f":admin:{target_player_id}"

    if redis_client:
        try:
            cached_response = redis_client.get(cache_key)
            if cached_response:
                return Response(json.loads(cached_response))
        except: pass

    # 3. Fetch from Redis (RAM)
    if redis_client:
        try:
            def _to_str(x, default=""):
                if x is None:
                    return default
                if isinstance(x, bytes):
                    try:
                        return x.decode()
                    except Exception:
                        return default
                return str(x)

            def _to_int(x, default=0):
                try:
                    return int(float(_to_str(x, str(default))))
                except Exception:
                    return default

            pipe = redis_client.pipeline()
            pipe.get(f"round:{round_id}:total_exposure")
            pipe.get(f"round:{round_id}:bet_count")
            pipe.hgetall(f"round:{round_id}:user_exposure")
            # Check if keys exist
            pipe.exists(f"round:{round_id}:total_exposure")
            results = pipe.execute()

            total_exposure = _to_str(results[0], "0.00") or "0.00"
            bet_count = _to_str(results[1], "0") or "0"
            user_exposure_map_raw = results[2] or {}
            # Normalize map keys/values to strings (Redis client may return bytes depending on config)
            user_exposure_map = {}
            try:
                for k, v in user_exposure_map_raw.items():
                    user_exposure_map[_to_str(k)] = _to_str(v, "0.00") or "0.00"
            except Exception:
                user_exposure_map = {}
            
            # If total_exposure is missing, it might just be a new round with no bets yet.
            # We only rebuild from DB if we are SURE the round should have data.
            # For now, let's just return 0 if it doesn't exist, instead of rebuilding from DB
            # which can be slow and might show 0 anyway if worker is lagging.
            
            # Filter for specific user if not staff
            if not is_admin:
                user_id_str = str(user_id)
                user_exposure = user_exposure_map.get(user_id_str, "0.00")
                user_exposure_map = {user_id_str: user_exposure}
            else:
                # If staff/admin, the user might want to filter by a specific player_id via query param
                if target_player_id:
                    user_exposure = user_exposure_map.get(str(target_player_id), "0.00")
                    user_exposure_map = {str(target_player_id): user_exposure}
                elif len(user_exposure_map) > 1:
                    # If no specific player_id requested and multiple exist, 
                    # just show the first one as requested "show only 1 player id"
                    first_key = next(iter(user_exposure_map))
                    user_exposure_map = {first_key: user_exposure_map[first_key]}

            # Get status from Redis if possible
            status_val = "BETTING"
            try:
                state_json = redis_client.get('current_game_state')
                if state_json:
                    status_val = json.loads(state_json).get('status', 'BETTING')
            except: pass
            status_norm = str(status_val or "BETTING").upper()

            # Prepare the new exposure list format
            exposure_list_formatted = []
            
            # CRITICAL: If status is RESULT, hide the chips (exposure) as requested
            # Chips should disappear after dice results are shown
            # Note: We keep them visible during CLOSED and ROLLING statuses
            if status_norm in ("RESULT", "COMPLETED"):
                res_data = {
                    'round_id': round_id,
                    'status': str(status_val).lower() if isinstance(status_val, str) else status_val,
                    'total_exposure': "0.00",
                    'total_bets': 0,
                    'unique_players': 0,
                    'exposure': []
                }
                if redis_client:
                    redis_client.set(cache_key, json.dumps(res_data), px=200)
                return Response(res_data)
            # We need usernames for the new format. 
            # Since Redis only stores IDs, we'll fetch usernames from DB for the active players.
            user_ids = []
            for uid in user_exposure_map.keys():
                try:
                    user_ids.append(int(str(uid)))
                except Exception:
                    continue
            from accounts.models import User
            users_map = {u.id: u.username for u in User.objects.filter(id__in=user_ids)}
            
            for uid_str, amount in user_exposure_map.items():
                try:
                    uid_int = int(str(uid_str))
                except Exception:
                    continue
                exposure_list_formatted.append({
                    "player_id": uid_int,
                    "username": users_map.get(uid_int, f"User {uid_int}"),
                    "exposure_amount": amount
                })

            res_data = {
                'round_id': round_id,
                'status': str(status_val).lower() if isinstance(status_val, str) else status_val,
                'total_exposure': total_exposure,
                'total_bets': _to_int(bet_count, 0),
                'unique_players': len(exposure_list_formatted),
                'exposure': exposure_list_formatted
            }
            
            # Cache the response for 200ms
            if redis_client:
                redis_client.set(cache_key, json.dumps(res_data), px=200)
                
            return Response(res_data)
        except Exception as e:
            logger.error(f"Redis exposure fetch failed: {e}", exc_info=True)

    # 4. Fallback to DB (Only if Redis fails)
    round_obj = get_object_or_404(GameRound, round_id=round_id)
    bets_query = Bet.objects.filter(round=round_obj)
    
    if not (request.user.is_staff or request.user.is_superuser):
        bets_query = bets_query.filter(user=request.user)
    else:
        # Admin filtering by player_id
        target_player_id = request.query_params.get('player_id')
        if target_player_id:
            bets_query = bets_query.filter(user_id=target_player_id)
        # If no target and we want to limit to 1 player as requested
        elif bets_query.exists():
            first_user_id = bets_query.values_list('user_id', flat=True).first()
            bets_query = bets_query.filter(user_id=first_user_id)

    from django.db.models import Sum, Count
    exposure_data = bets_query.values('user_id', 'user__username').annotate(
        exposure_amount=Sum('chip_amount'),
        bet_count=Count('id')
    )

    exposure_list_formatted = []
    for e in exposure_data:
        exposure_list_formatted.append({
            "player_id": e['user_id'],
            "username": e['user__username'],
            "exposure_amount": str(e['exposure_amount'])
        })

    return Response({
        'round_id': round_id,
        'status': round_obj.status,
        'total_exposure': str(bets_query.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0),
        'total_bets': bets_query.count(),
        'unique_players': len(exposure_list_formatted),
        'exposure': exposure_list_formatted
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_payments(request):
    """
    Get all pending payments (legacy 10% commission from payouts).
    Note: New rounds follow the 'No Commission' rule and will not generate these records.
    Returns: List of pending payments with round, user, and commission details.
    
    Query params:
    - round_id: (optional) Filter by specific round ID
    - user_id: (optional) Filter by specific user ID (admin only)
    - limit: (optional) Limit number of results (default: 100)
    """
    logger.info(f"User {request.user.username} fetching pending payments")
    from accounts.models import PendingPayment
    from django.db.models import Sum
    
    # Check if user is admin for user_id filtering
    is_admin = request.user.is_staff or request.user.is_superuser
    
    # Get query parameters
    round_id = request.query_params.get('round_id')
    user_id = request.query_params.get('user_id')
    limit = int(request.query_params.get('limit', 100))
    
    # Build query
    payments_query = PendingPayment.objects.select_related('round', 'user', 'bet')
    
    # Filter by round if provided
    if round_id:
        payments_query = payments_query.filter(round__round_id=round_id)
    
    # Filter by user if provided (admin only)
    if user_id:
        if is_admin:
            payments_query = payments_query.filter(user_id=user_id)
        else:
            return Response(
                {'error': 'Only admins can filter by user_id'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    elif not is_admin:
        # Non-admin users can only see their own pending payments
        payments_query = payments_query.filter(user=request.user)
    
    # Order by most recent first
    payments = payments_query.order_by('-created_at')[:limit]
    
    # Calculate totals
    total_commission = payments_query.aggregate(
        Sum('commission_amount')
    )['commission_amount__sum'] or Decimal('0.00')
    
    # Serialize payments
    payments_data = []
    for payment in payments:
        payments_data.append({
            'id': payment.id,
            'round_id': payment.round.round_id,
            'round_status': payment.round.status,
            'user': {
                'id': payment.user.id,
                'username': payment.user.username,
            },
            'bet_id': payment.bet.id,
            'bet_number': payment.bet.number,
            'bet_amount': str(payment.bet.chip_amount),
            'total_payout': str(payment.total_payout),
            'winner_amount': str(payment.winner_amount),
            'commission_amount': str(payment.commission_amount),
            'created_at': payment.created_at.isoformat(),
        })
    
    return Response({
        'pending_payments': payments_data,
        'total_commission': str(total_commission),
        'count': len(payments_data),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def ending_payment_for_user(request, user_id):
    """
    Get ending payment (total pending commission) for a client/user.
    For use by client-payments app: replace "Total Client PnL" with "Ending Payment" using this value.
    Returns: user_id, username, ending_payment (sum of PendingPayment.commission_amount for this user).
    """
    from accounts.models import PendingPayment
    from django.db.models import Sum

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    total = PendingPayment.objects.filter(user_id=user_id).aggregate(
        total=Sum('commission_amount')
    )['total']
    ending_payment = total if total is not None else Decimal('0.00')

    return Response({
        'user_id': user.id,
        'username': user.username,
        'ending_payment': str(ending_payment),
    })

# ─── Cricket Betting Views ────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def cricket_live(request):
    """Return current live cricket events cached by the cricket poller."""
    try:
        r = redis.Redis(
            host=getattr(settings, 'REDIS_HOST', '127.0.0.1'),
            port=int(getattr(settings, 'REDIS_PORT', 6379)),
            password=getattr(settings, 'REDIS_PASSWORD', None) or None,
            decode_responses=True,
        )
        raw = r.get('cricket:live_events')
        events = json.loads(raw) if raw else []
    except Exception:
        events = []
    return Response({'events': events})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_cricket_bet(request):
    from .models import CricketBet
    from accounts.models import Wallet, Transaction
    data = request.data
    required = ['event_id', 'event_name', 'market_id', 'market_name',
                'outcome_id', 'outcome_name', 'odds', 'stake']
    for field in required:
        if field not in data:
            return Response({'error': f'Missing field: {field}'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        stake = int(data['stake'])
        odds = Decimal(str(data['odds']))
    except (ValueError, TypeError):
        return Response({'error': 'Invalid stake or odds'}, status=status.HTTP_400_BAD_REQUEST)
    if stake <= 0:
        return Response({'error': 'Stake must be positive'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(user=request.user)
        if wallet.balance < stake:
            return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)
        wallet.balance -= stake
        wallet.save()
        potential_payout = int(stake * odds)
        bet = CricketBet.objects.create(
            user=request.user,
            event_id=data['event_id'],
            event_name=data['event_name'],
            market_id=data['market_id'],
            market_name=data['market_name'],
            outcome_id=data['outcome_id'],
            outcome_name=data['outcome_name'],
            odds=odds,
            stake=stake,
            potential_payout=potential_payout,
        )
        Transaction.objects.create(
            user=request.user,
            transaction_type='DEBIT',
            amount=stake,
            description=f'Cricket bet #{bet.pk}',
        )
    return Response({'bet_id': bet.pk, 'stake': stake, 'potential_payout': potential_payout},
                    status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_cricket_bets(request):
    from .models import CricketBet
    bets = CricketBet.objects.filter(user=request.user).order_by('-created_at')[:50]
    data = [
        {
            'id': b.pk,
            'event_name': b.event_name,
            'market_name': b.market_name,
            'outcome_name': b.outcome_name,
            'odds': str(b.odds),
            'stake': b.stake,
            'potential_payout': b.potential_payout,
            'status': b.status,
            'payout_amount': b.payout_amount,
            'created_at': b.created_at.isoformat(),
        }
        for b in bets
    ]
    return Response(data)


# ─── Cock Fight Views ─────────────────────────────────────────────────────────

COCKFIGHT_VIDEO_STREAM_SIGNER = TimestampSigner(salt='cockfight-round-video-stream-v1')


def build_cockfight_signed_stream_url(request, pk: int) -> str:
    """Time-limited signed URL for GET .../meron-wala/video-stream/?token=..."""
    token = COCKFIGHT_VIDEO_STREAM_SIGNER.sign(str(pk))
    path = reverse('cockfight_video_stream')
    return request.build_absolute_uri(path) + '?' + urlencode({'token': token})


def _serialize_latest_cockfight_round_video(request):
    """Metadata for the latest round video; playable `url` only when JWT auth and start time reached."""
    from .models import CockFightRoundVideo

    rv = CockFightRoundVideo.objects.order_by('-id').first()
    if not rv or not rv.video:
        return None
    ensure_cockfight_round_video_duration(rv)
    # Do not expose uploaded_at — it reveals pre-record timing vs simulated "live".
    out = {
        'round_id': rv.pk,
        # Clients align device clock skew so everyone uses the same "now" vs `start` (pseudo-live sync).
        'server_time': timezone.now().isoformat(),
    }
    if rv.scheduled_start:
        out['start'] = rv.scheduled_start.isoformat()
    else:
        out['start'] = None
    if rv.scheduled_start and rv.duration_seconds:
        from datetime import timedelta as _td
        out['end_time'] = (rv.scheduled_start + _td(seconds=rv.duration_seconds)).isoformat()
    else:
        out['end_time'] = None
    if request.user.is_authenticated:
        if cockfight_consumer_stream_active(rv):
            out['url'] = build_cockfight_signed_stream_url(request, rv.pk)
        else:
            out['url'] = None
        out['requires_authentication'] = False
    else:
        out['url'] = None
        out['requires_authentication'] = True
    return out


@require_http_methods(['GET', 'HEAD'])
def cockfight_video_stream(request):
    """Serve video bytes only with a valid signed token (issued from authenticated cock_fight_info)."""
    token = request.GET.get('token')
    if not token:
        return HttpResponseForbidden('Missing token')
    max_age = getattr(settings, 'COCKFIGHT_VIDEO_STREAM_MAX_AGE', 60 * 60 * 6)
    try:
        pk = int(COCKFIGHT_VIDEO_STREAM_SIGNER.unsign(token, max_age=max_age))
    except BadSignature:
        return HttpResponseForbidden('Invalid token')
    except SignatureExpired:
        return HttpResponseForbidden('Expired token')
    from .models import CockFightRoundVideo

    rv = CockFightRoundVideo.objects.filter(pk=pk).first()
    if not rv or not rv.video:
        raise Http404()
    from .admin_utils import is_admin

    ensure_cockfight_round_video_duration(rv)
    preview_ok = request.user.is_authenticated and is_admin(request.user)
    if not preview_ok:
        if not cockfight_consumer_stream_active(rv):
            now = timezone.now()
            if rv.scheduled_start and now < rv.scheduled_start:
                return HttpResponseForbidden('Stream not started yet')
            return HttpResponseForbidden('Broadcast ended')
    file_path = rv.video.path
    if not os.path.isfile(file_path):
        raise Http404()
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = 'video/mp4'

    # Use X-Accel-Redirect so nginx serves the bytes directly from disk —
    # avoids buffering the full file through gunicorn and handles Range requests natively.
    # Nginx internal location /x-accel-cockfight/ → /root/fight/media/cockfight_videos/
    filename = os.path.basename(file_path)
    from django.http import HttpResponse

    resp = HttpResponse(content_type=content_type)
    resp['X-Accel-Redirect'] = f'/x-accel-cockfight/{filename}'
    resp['Accept-Ranges'] = 'bytes'
    resp['Cache-Control'] = 'private, max-age=3600'
    resp['Content-Disposition'] = 'inline'
    return resp


@api_view(['GET'])
@permission_classes([AllowAny])
def cock_fight_info(request):
    from .models import CockFightSession

    latest_round_video = _serialize_latest_cockfight_round_video(request)
    session = CockFightSession.objects.filter(status='OPEN').order_by('-id').first()
    if not session:
        return Response({
            'session': None,
            'open': False,
            'latest_round_video': latest_round_video,
        })
    return Response({
        'session': session.pk,
        'open': True,
        'created_at': session.created_at.isoformat(),
        'latest_round_video': latest_round_video,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def meron_wala_latest_round_video(request):
    """GET latest cockfight round video only (same file as shown on game-admin cockfight-round-videos)."""
    latest = _serialize_latest_cockfight_round_video(request)
    return Response({'latest_round_video': latest})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_cock_fight_bet(request):
    from .models import CockFightSession, CockFightBet
    from accounts.models import Wallet, Transaction
    side = request.data.get('side', '').upper()
    if side not in ('RED', 'BLUE'):
        return Response({'error': 'side must be RED or BLUE'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        stake = int(request.data['stake'])
    except (KeyError, ValueError, TypeError):
        return Response({'error': 'Invalid stake'}, status=status.HTTP_400_BAD_REQUEST)
    if stake <= 0:
        return Response({'error': 'Stake must be positive'}, status=status.HTTP_400_BAD_REQUEST)

    session = CockFightSession.objects.filter(status='OPEN').order_by('-id').first()
    if not session:
        return Response({'error': 'No open session'}, status=status.HTTP_400_BAD_REQUEST)

    odds = Decimal('9.00')
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(user=request.user)
        if wallet.balance < stake:
            return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)
        wallet.balance -= stake
        wallet.save()
        potential_payout = int(stake * odds)
        bet = CockFightBet.objects.create(
            user=request.user,
            session=session,
            side=side,
            stake=stake,
            odds=odds,
            potential_payout=potential_payout,
        )
        Transaction.objects.create(
            user=request.user,
            transaction_type='DEBIT',
            amount=stake,
            description=f'Cock fight bet #{bet.pk}',
        )
    return Response({'bet_id': bet.pk, 'stake': stake, 'side': side, 'potential_payout': potential_payout},
                    status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_cock_fight_bets(request):
    from .models import CockFightBet
    bets = CockFightBet.objects.filter(user=request.user).order_by('-created_at')[:50]
    data = [
        {
            'id': b.pk,
            'session': b.session_id,
            'side': b.side,
            'stake': b.stake,
            'odds': str(b.odds),
            'potential_payout': b.potential_payout,
            'status': b.status,
            'payout_amount': b.payout_amount,
            'created_at': b.created_at.isoformat(),
        }
        for b in bets
    ]
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def settle_cock_fight(request):
    from .models import CockFightSession, CockFightBet
    from accounts.models import Wallet, Transaction
    from django.contrib.auth import get_user_model
    User_ = get_user_model()
    if not (request.user.is_staff or request.user.is_superuser):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    winner = request.data.get('winner', '').upper()
    if winner not in ('RED', 'BLUE'):
        return Response({'error': 'winner must be RED or BLUE'}, status=status.HTTP_400_BAD_REQUEST)
    session_id = request.data.get('session_id')
    if session_id:
        session = get_object_or_404(CockFightSession, pk=session_id, status='OPEN')
    else:
        session = CockFightSession.objects.filter(status='OPEN').order_by('-id').first()
        if not session:
            return Response({'error': 'No open session'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        session.status = 'SETTLED'
        session.winner = winner
        session.settled_at = timezone.now()
        session.save()
        bets = CockFightBet.objects.select_for_update().filter(session=session, status='PENDING')
        won_count = lost_count = 0
        for bet in bets:
            if bet.side == winner:
                bet.status = 'WON'
                bet.payout_amount = bet.potential_payout
                bet.settled_at = timezone.now()
                bet.save()
                wallet = Wallet.objects.select_for_update().get(user=bet.user)
                wallet.balance += bet.payout_amount
                wallet.save()
                Transaction.objects.create(
                    user=bet.user,
                    transaction_type='CREDIT',
                    amount=bet.payout_amount,
                    description=f'Cock fight win #{bet.pk}',
                )
                won_count += 1
            else:
                bet.status = 'LOST'
                bet.settled_at = timezone.now()
                bet.save()
                lost_count += 1
    return Response({'session': session.pk, 'winner': winner, 'won': won_count, 'lost': lost_count})


# ---------------------------------------------------------------------------
# Meron / Wala / Draw betting (sabong-style fixed odds)
# Odds (decimal, includes stake):  MERON=1.90, WALA=1.92, DRAW=4.46
# Example: bet 100 on MERON → win returns 190 total (90 profit + 100 stake back)
# ---------------------------------------------------------------------------
MERON_WALA_ODDS = {
    'MERON': Decimal('1.90'),
    'WALA': Decimal('1.92'),
    'DRAW': Decimal('4.46'),
}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_meron_wala_bet(request):
    """
    Place a bet on MERON / WALA / DRAW.
    POST /api/game/meron-wala/bet/
    Body: { "side": "MERON" | "WALA" | "DRAW", "stake": <int>, "event_id": <optional int> }
    """
    from .models import CockFightSession, CockFightBet
    from accounts.models import Wallet, Transaction

    if request.user.is_staff or request.user.is_superuser:
        return Response({'error': 'Admins are not allowed to participate in the game.'},
                        status=status.HTTP_403_FORBIDDEN)

    side = (request.data.get('side') or '').upper().strip()
    if side not in MERON_WALA_ODDS:
        return Response({'error': 'side must be MERON, WALA or DRAW'},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        stake = int(request.data['stake'])
    except (KeyError, ValueError, TypeError):
        return Response({'error': 'Invalid stake'}, status=status.HTTP_400_BAD_REQUEST)
    if stake <= 0:
        return Response({'error': 'Stake must be positive'}, status=status.HTTP_400_BAD_REQUEST)

    max_bet_limit = int(get_game_setting('MAX_BET', 50000))
    if stake > max_bet_limit:
        return Response({'error': f'Maximum bet amount is {max_bet_limit}'},
                        status=status.HTTP_400_BAD_REQUEST)

    odds = MERON_WALA_ODDS[side]
    potential_payout = int(Decimal(stake) * odds)

    with transaction.atomic():
        session = (CockFightSession.objects
                   .select_for_update()
                   .filter(status='OPEN')
                   .order_by('-id')
                   .first())
        if not session:
            session = CockFightSession.objects.create(status='OPEN')

        wallet = Wallet.objects.select_for_update().get(user=request.user)
        balance_before = int(wallet.balance)
        if balance_before < stake:
            return Response({'error': 'Insufficient balance'},
                            status=status.HTTP_400_BAD_REQUEST)

        wallet.balance = balance_before - stake
        wallet.save(update_fields=['balance'])
        balance_after = int(wallet.balance)

        bet = CockFightBet.objects.create(
            user=request.user,
            session=session,
            side=side,
            stake=stake,
            odds=odds,
            potential_payout=potential_payout,
        )
        Transaction.objects.create(
            user=request.user,
            transaction_type='BET',
            amount=stake,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f'Meron/Wala bet #{bet.pk} on {side}',
        )

        # Keep Redis balance cache in sync so wallet API stays fast/correct.
        if redis_client:
            try:
                redis_client.set(f'user_balance:{request.user.id}', str(wallet.balance), ex=86400)
            except Exception:
                pass

    return Response({
        'success': True,
        'bet_id': bet.pk,
        'session_id': session.pk,
        'side': side,
        'stake': stake,
        'odds': str(odds),
        'potential_payout': potential_payout,
        'wallet_balance': str(wallet.balance),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def settle_meron_wala_round(request):
    """
    Admin: mark the result for a Meron/Wala/Draw (cockfight) round and credit winners.
    Staff/superuser only. Use from admin tools or a trusted client with a staff JWT.

    POST /api/game/meron-wala/admin/settle-round/
    Body (JSON):
      { "round_id": <int>,  "winner": "MERON" | "WALA" | "DRAW" }
    (Legacy alias: "session_id" is accepted if "round_id" is omitted — same value as round id.)
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    winner = (request.data.get('winner') or '').upper().strip()
    raw_id = request.data.get('round_id', request.data.get('session_id'))
    try:
        round_id = int(raw_id)
    except (TypeError, ValueError):
        return Response(
            {'error': 'round_id is required and must be an integer'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from .meron_wala_settlement import run_meron_wala_settlement

    payload, code = run_meron_wala_settlement(round_id, winner)
    if code == 200:
        return Response(payload, status=status.HTTP_200_OK)
    if code == 404:
        return Response(payload, status=status.HTTP_404_NOT_FOUND)
    return Response(payload, status=status.HTTP_400_BAD_REQUEST)
