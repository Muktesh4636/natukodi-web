from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from decimal import Decimal
import redis
import json
import logging

logger = logging.getLogger('game')

from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction
from accounts.models import User, Wallet, Transaction # Added User, Wallet, Transaction for exposure API and other uses
from .serializers import (
    GameRoundSerializer, BetSerializer, CreateBetSerializer, DiceResultSerializer,
    RoundPredictionSerializer, CreatePredictionSerializer
)
from .utils import get_game_setting, get_all_game_settings, calculate_current_timer

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
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
        }
        if hasattr(settings, 'REDIS_PASSWORD') and settings.REDIS_PASSWORD:
            redis_kwargs['password'] = settings.REDIS_PASSWORD
        redis_client = redis.Redis(**redis_kwargs)
        redis_client.ping()
except (redis.ConnectionError, redis.TimeoutError, redis.AuthenticationError, AttributeError, Exception) as e:
    logger.warning(f"Redis connection failed: {e}. Falling back to database-only mode.")
    redis_client = None


def get_dice_mode():
    """Get dice result mode: 'manual' or 'random'"""
    try:
        setting = GameSettings.objects.get(key='dice_mode')
        return setting.value
    except GameSettings.DoesNotExist:
        # Default to 'random' if not set
        GameSettings.objects.create(key='dice_mode', value='random', description='Dice result mode: manual or random')
        return 'random'


def set_dice_mode(mode):
    """Set dice result mode: 'manual' or 'random'"""
    if mode not in ['manual', 'random']:
        return False
    GameSettings.objects.update_or_create(
        key='dice_mode',
        defaults={'value': mode, 'description': 'Dice result mode: manual or random'}
    )
    return True


from rest_framework_simplejwt.authentication import JWTAuthentication

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def current_round(request):
    """Get current game round status from Redis (High Performance)"""
    if redis_client:
        try:
            state_json = redis_client.get('current_game_state')
            if state_json:
                state = json.loads(state_json)
                
                # Add legacy timer field for Unity compatibility
                now = int(timezone.now().timestamp())
                end_time = state.get('end_time', 0)
                state['timer'] = max(0, end_time - now)
                
                return Response(state)
        except Exception as e:
            logger.error(f"Redis error in current_round: {e}")
    
    # Fallback to database if Redis fails
    round_obj = GameRound.objects.order_by('-start_time').first()
    if not round_obj:
        return Response({'status': 'WAITING', 'message': 'No rounds found'}, status=404)

    # Calculate absolute end_time for fallback
    # Assuming 80s total round duration
    round_end_time = get_game_setting('ROUND_END_TIME', 80)
    end_timestamp = int(round_obj.start_time.timestamp() + round_end_time)
    remaining_timer = max(0, int(end_timestamp - timezone.now().timestamp()))

    return Response({
        'round_id': round_obj.round_id,
        'status': round_obj.status,
        'end_time': end_timestamp,
        'timer': remaining_timer,
        'server_time': int(timezone.now().timestamp()),
        'is_rolling': round_obj.status == 'ROLLING'
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
local new_balance = redis.call('INCRBYFLOAT', KEYS[1], -amount)

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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def place_bet(request):
    """Place a bet on a number using Redis-First logic for high performance"""
    serializer = CreateBetSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    number = serializer.validated_data['number']
    chip_amount = float(serializer.validated_data['chip_amount'])
    if chip_amount <= 0:
        return Response({'error': 'Invalid bet amount'}, status=status.HTTP_400_BAD_REQUEST)
    user_id = request.user.id
    username = request.user.username

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
                end_time = state.get('end_time', 0)
                
                # Check if betting is closed
                if status_val != "BETTING":
                    return Response({'error': 'Betting is closed for this round'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Safety check: if end_time is in the past, engine might be lagging
                if end_time > 0 and int(timezone.now().timestamp()) > end_time:
                    return Response({'error': 'Betting period has expired'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Redis error fetching round: {e}")

    # Fallback to DB for round if Redis fails
    if not round_id:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if not round_obj or round_obj.status != 'BETTING':
            return Response({'error': 'No active betting round'}, status=status.HTTP_400_BAD_REQUEST)
        round_id = round_obj.round_id

    # 3. Redis-First Atomic Placement (Lua Script)
    if redis_client:
        try:
            balance_key = f"user_balance:{user_id}"
            
            # Ensure balance is in Redis (warm up if needed) - ATOMIC using SETNX
            # SETNX ensures only ONE request sets the initial balance, preventing race conditions
            current_redis_balance = redis_client.get(balance_key)
            if current_redis_balance is None:
                wallet = Wallet.objects.get(user_id=user_id)
                # Use SET with NX flag to atomically set balance only if key doesn't exist
                # This prevents race condition where multiple requests all set the same stale balance
                was_set = redis_client.set(balance_key, str(wallet.balance), ex=3600, nx=True)
                # If SETNX failed (another request set it first), get the value they set
                if not was_set:
                    # Another request set it, get the current value (should be set now)
                    current_redis_balance = redis_client.get(balance_key)
                    if current_redis_balance is None:
                        # Still None - something went wrong, refresh from DB and set anyway
                        wallet.refresh_from_db()
                        redis_client.set(balance_key, str(wallet.balance), ex=3600)

            keys = [
                balance_key,
                f"round:{round_id}:total_exposure",
                f"round:{round_id}:user_exposure",
                f"round:{round_id}:bet_count",
                f"round_total_amount:{round_id}", # Legacy key for compatibility
                f"round_total_bets:{round_id}"    # Legacy key for compatibility
            ]
            
            # Execute Lua script with TTL (3600 seconds = 1 hour)
            # Keys: [balance, total_exp, user_exp, bet_count, legacy_amount, legacy_bets]
            result = redis_client.eval(PLACE_BET_LUA, 6, *keys, chip_amount, user_id, 3600)
            success, response_val = result[0], result[1]

            if not success:
                return Response({'error': response_val}, status=status.HTTP_400_BAD_REQUEST)

            new_balance = response_val

            # 4. Queue the Bet for DB processing using Redis Stream
            bet_data = {
                'user_id': str(user_id),
                'username': username,
                'round_id': round_id,
                'number': str(number),
                'chip_amount': str(chip_amount),
                'timestamp': timezone.now().isoformat()
            }
            # Use XADD to add bet to stream (creates stream if doesn't exist)
            redis_client.xadd('bet_stream', bet_data, maxlen=10000)  # Keep last 10k bets

            return Response({
                'message': 'Bet placed successfully',
                'wallet_balance': "{:.2f}".format(float(new_balance)),
                'round': {
                    'round_id': round_id,
                    'total_bets': int(redis_client.get(f"round_total_bets:{round_id}") or 0),
                    'total_amount': "{:.2f}".format(float(redis_client.get(f"round_total_amount:{round_id}") or 0))
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Redis-First betting failed, falling back to DB: {e}")
            # Fallback to old database method when Redis fails
            pass
    
    # FALLBACK: Use old database method when Redis is unavailable
    try:
        # Get round object
        round_obj = GameRound.objects.order_by('-start_time').first()
        if not round_obj:
            return Response({'error': 'No active round'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check timing
        timer = calculate_current_timer(round_obj.start_time)
        betting_close_time = get_game_setting('BETTING_CLOSE_TIME', 30)
        if timer >= betting_close_time:
            return Response({'error': f'Betting closed at {betting_close_time}s'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Atomic balance update using F() expression (database-level atomicity)
        with transaction.atomic():
            # Get balance_before first for transaction log
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            balance_before = wallet.balance
            
            # Atomic balance deduction using F() expression
            updated = Wallet.objects.filter(
                user=request.user,
                balance__gte=Decimal(str(chip_amount))
            ).update(balance=F('balance') - Decimal(str(chip_amount)))
            
            if updated == 0:
                return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Get updated balance
            wallet.refresh_from_db()
            balance_after = wallet.balance
            
            # Create bet
            bet = Bet.objects.create(
                user=request.user,
                round=round_obj,
                number=number,
                chip_amount=Decimal(str(chip_amount))
            )
            
            # Create transaction log
            Transaction.objects.create(
                user=request.user,
                transaction_type='BET',
                amount=Decimal(str(chip_amount)),
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Bet on number {number} in round {round_obj.round_id}"
            )
            
            # Update round stats
            round_obj.total_bets += 1
            round_obj.total_amount += Decimal(str(chip_amount))
            round_obj.save()
        
        serializer = BetSerializer(bet)
        return Response({
            'bet': serializer.data,
            'wallet_balance': str(wallet.balance),
            'round': {
                'round_id': round_obj.round_id,
                'total_bets': round_obj.total_bets,
                'total_amount': str(round_obj.total_amount)
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.exception(f"Database fallback betting failed: {e}")
        return Response({'error': 'Failed to place bet. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def remove_bet(request, number):
    """Remove a bet for a specific number"""
    logger.info(f"Remove bet request by user {request.user.username} (ID: {request.user.id}) for number {number}")
    
    # 1. Get current round state (Prefer Redis)
    round_id = None
    if redis_client:
        try:
            state_json = redis_client.get('current_game_state')
            if state_json:
                state = json.loads(state_json)
                round_id = state.get('round_id')
                status_val = state.get('status')
                
                if status_val != "BETTING":
                    return Response({'error': 'Cannot remove bet after betting closes'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Redis error in remove_bet: {e}")

    # 2. Get round object
    try:
        if round_id:
            round_obj = GameRound.objects.get(round_id=round_id)
        else:
            round_obj = GameRound.objects.order_by('-start_time').first()
    except GameRound.DoesNotExist:
        return Response({'error': 'Round not found'}, status=status.HTTP_404_NOT_FOUND)

    if not round_obj or round_obj.status != 'BETTING':
        return Response({'error': 'Betting is closed for this round'}, status=status.HTTP_400_BAD_REQUEST)

    # Get the bet
    try:
        bet = Bet.objects.get(user=request.user, round=round_obj, number=number)
    except Bet.DoesNotExist:
        logger.warning(f"Remove bet failed for user {request.user.username}: Bet on number {number} not found in round {round_obj.round_id}")
        return Response({'error': 'Bet not found'}, status=status.HTTP_404_NOT_FOUND)

    # Store bet amount before deleting
    refund_amount = bet.chip_amount

    try:
        with transaction.atomic():
            # Refund the bet amount
            wallet = request.user.wallet
            balance_before = wallet.balance
            wallet.add(refund_amount)
            balance_after = wallet.balance

            # Update round stats in Redis for high performance and to avoid DB row contention
            if redis_client:
                try:
                    # 1. Update user balance in Redis (CRITICAL for Redis-First betting)
                    balance_key = f"user_balance:{request.user.id}"
                    # Use set instead of incrbyfloat to ensure absolute sync with DB
                    redis_client.set(balance_key, str(wallet.balance), ex=3600)
                    
                    # 2. Decrement totals in Redis
                    new_total_bets = redis_client.decr(f"round_total_bets:{round_obj.round_id}")
                    if new_total_bets < 0:
                        redis_client.set(f"round_total_bets:{round_obj.round_id}", 0)
                        new_total_bets = 0
                    
                    new_total_amount = redis_client.incrbyfloat(f"round_total_amount:{round_obj.round_id}", -float(refund_amount))
                    if new_total_amount < 0:
                        redis_client.set(f"round_total_amount:{round_obj.round_id}", 0)
                        new_total_amount = 0
                    
                    # Update local object for response
                    round_obj.total_bets = max(0, int(new_total_bets))
                    round_obj.total_amount = max(Decimal('0.00'), Decimal(str(new_total_amount)))
                except Exception as redis_err:
                    logger.error(f"Redis error updating round stats or balance: {redis_err}")
                    # Fallback to DB
                    round_obj.total_bets = max(0, round_obj.total_bets - 1)
                    round_obj.total_amount = max(Decimal('0.00'), round_obj.total_amount - refund_amount)
                    round_obj.save()
            else:
                # Fallback to DB
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
                description=f"Refund bet on number {number} in round {round_obj.round_id}"
            )

            # Delete the bet
            bet.delete()
            logger.info(f"Bet removed and refunded: User {request.user.username}, Round {round_obj.round_id}, Num {number}, Amount {refund_amount}")
    except Exception as e:
        logger.exception(f"Unexpected error removing bet for user {request.user.username}: {e}")
        return Response({'error': 'Internal server error during refund'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'message': f'Bet on number {number} removed',
        'refund_amount': str(refund_amount),
        'wallet_balance': str(wallet.balance),
        'round': {
            'round_id': round_obj.round_id,
            'total_bets': round_obj.total_bets,
            'total_amount': str(round_obj.total_amount)
        }
    })


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def remove_last_bet(request):
    """
    GET: View the user's last (most recent) bet for the current round
    DELETE: Remove and refund the user's last (most recent) bet for the current round
    """
    logger.info(f"{request.method} last bet request by user {request.user.username} (ID: {request.user.id})")
    
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
        except Exception as e:
            logger.error(f"Redis error in remove_last_bet: {e}")

    # 2. Get round object
    try:
        if round_id:
            round_obj = GameRound.objects.get(round_id=round_id)
        else:
            round_obj = GameRound.objects.order_by('-start_time').first()
    except GameRound.DoesNotExist:
        return Response({'error': 'Round not found'}, status=status.HTTP_404_NOT_FOUND)

    if not round_obj:
        return Response({'error': 'No active round'}, status=status.HTTP_400_BAD_REQUEST)

    # Get the user's last (most recent) bet for this round
    try:
        bet = Bet.objects.filter(user=request.user, round=round_obj).order_by('-created_at').first()
        if not bet:
            return Response({'error': 'No bets found in this round'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error finding last bet: {e}")
        return Response({'error': 'Error finding last bet'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # If it's a GET request, just return the bet details
    if request.method == 'GET':
        return Response({
            'bet': {
                'id': bet.id,
                'number': bet.number,
                'chip_amount': "{:.2f}".format(float(bet.chip_amount)),
                'created_at': bet.created_at.isoformat(),
                'is_winner': bet.is_winner,
                'payout_amount': "{:.2f}".format(float(bet.payout_amount)) if bet.payout_amount else None
            },
            'round': {
                'round_id': round_obj.round_id,
                'status': round_obj.status
            },
            'wallet_balance': "{:.2f}".format(float(request.user.wallet.balance)) if hasattr(request.user, 'wallet') else "0.00"
        })

    # If it's a DELETE request, proceed with removal
    if status_val != "BETTING" and round_obj.status != "BETTING":
        return Response({'error': 'Cannot remove bet after betting closes'}, status=status.HTTP_400_BAD_REQUEST)

    # Store bet details before deleting
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
                    # 1. Update user balance in Redis (CRITICAL for Redis-First betting)
                    balance_key = f"user_balance:{request.user.id}"
                    # Use set instead of incrbyfloat to ensure absolute sync with DB
                    redis_client.set(balance_key, str(wallet.balance), ex=3600)
                    
                    # 2. Decrement totals in Redis
                    new_total_bets = redis_client.decr(f"round_total_bets:{round_obj.round_id}")
                    if new_total_bets < 0:
                        redis_client.set(f"round_total_bets:{round_obj.round_id}", 0)
                        new_total_bets = 0
                    
                    new_total_amount = redis_client.incrbyfloat(f"round_total_amount:{round_obj.round_id}", -float(refund_amount))
                    if new_total_amount < 0:
                        redis_client.set(f"round_total_amount:{round_obj.round_id}", 0)
                        new_total_amount = 0
                    
                    round_obj.total_bets = max(0, int(new_total_bets))
                    round_obj.total_amount = max(Decimal('0.00'), Decimal(str(new_total_amount)))
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
                description=f"Refund last bet on number {bet_number} in round {round_obj.round_id}"
            )

            # Delete the bet
            bet.delete()
            logger.info(f"Last bet removed and refunded: User {request.user.username}, Round {round_obj.round_id}, Num {bet_number}, Amount {refund_amount}")
    except Exception as e:
        logger.exception(f"Unexpected error removing last bet for user {request.user.username}: {e}")
        return Response({'error': 'Internal server error during refund'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'message': f'Last bet on number {bet_number} removed',
        'refund_amount': str(refund_amount),
        'bet_number': bet_number,
        'wallet_balance': str(wallet.balance),
        'round': {
            'round_id': round_obj.round_id,
            'total_bets': round_obj.total_bets,
            'total_amount': str(round_obj.total_amount)
        }
    })


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


@api_view(['POST'])
@permission_classes([IsAdminUser])
def set_dice_result(request):
    """Admin: Set dice result for current round"""
    result = request.data.get('result')
    logger.info(f"Admin {request.user.username} setting dice result: {result}")
    if not result or result < 1 or result > 6:
        logger.warning(f"Admin {request.user.username} provided invalid result: {result}")
        return Response({'error': 'Invalid dice result (1-6)'}, status=status.HTTP_400_BAD_REQUEST)

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
    
    if not round_obj:
        logger.warning(f"Admin {request.user.username} failed to set result: No active round")
        return Response({'error': 'No active round'}, status=status.HTTP_400_BAD_REQUEST)

    # Check if individual dice values are set - if so, recalculate result from them
    dice_values = [round_obj.dice_1, round_obj.dice_2, round_obj.dice_3, 
                   round_obj.dice_4, round_obj.dice_5, round_obj.dice_6]
    
    valid_dice = [v for v in dice_values if v is not None]
    if valid_dice:
        # Some or all individual dice values are set - recalculate result from them
        from .utils import determine_winning_number
        result = determine_winning_number(valid_dice)
    
    try:
        with transaction.atomic():
            # Set dice result (either from parameter or recalculated from dice values)
            round_obj.dice_result = result
            round_obj.status = 'RESULT'
            round_obj.result_time = timezone.now()
            round_obj.save()

            # Create dice result record
            DiceResult.objects.update_or_create(
                round=round_obj,
                defaults={
                    'result': result,
                    'set_by': request.user
                }
            )

            # Update Redis if available
            if redis_client:
                try:
                    round_data = redis_client.get('current_round')
                    if round_data:
                        round_data = json.loads(round_data)
                        round_data['dice_result'] = result
                        round_data['status'] = 'RESULT'
                        redis_client.set('current_round', json.dumps(round_data))
                    
                    # CRITICAL: Clear the last_round_results_cache so the API shows fresh manual data
                    redis_client.delete('last_round_results_cache')
                    logger.info("Cleared last_round_results_cache after manual result set")
                except Exception as e:
                    logger.error(f"Redis sync error in set_dice_result: {e}")

            # Calculate payouts - get dice values from round
            dice_values = [
                round_obj.dice_1, round_obj.dice_2, round_obj.dice_3,
                round_obj.dice_4, round_obj.dice_5, round_obj.dice_6
            ]
            calculate_payouts(round_obj, dice_result=result, dice_values=dice_values)
            
            # Mark correct predictions
            mark_correct_predictions(round_obj, dice_values=dice_values)
            
            logger.info(f"Result {result} set successfully for round {round_obj.round_id} and payouts calculated")
    except Exception as e:
        logger.exception(f"Unexpected error in set_dice_result by admin {request.user.username}: {e}")
        return Response({'error': 'Internal server error setting result'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = GameRoundSerializer(round_obj)
    data = serializer.data
    
    # Add dynamic timer to response
    timer = 0
    if redis_client:
        try:
            redis_timer = redis_client.get('round_timer')
            if redis_timer:
                timer = int(redis_timer)
        except Exception:
            pass
            
    if timer <= 0:
        timer = calculate_current_timer(round_obj.start_time, round_obj.round_end_seconds)
        
    data['timer'] = timer
    
    # Fetch real-time totals from Redis if available
    if redis_client:
        try:
            total_bets_val = redis_client.get(f"round_total_bets:{round_obj.round_id}")
            if total_bets_val:
                data['total_bets'] = int(total_bets_val)
            
            total_amount_val = redis_client.get(f"round_total_amount:{round_obj.round_id}")
            if total_amount_val:
                data['total_amount'] = "{:.2f}".format(float(total_amount_val))
        except Exception as redis_err:
            logger.error(f"Error fetching totals from Redis: {redis_err}")

    # Add is_rolling flag to ensure animation state is synced
    rolling_start = get_game_setting('DICE_ROLL_TIME', 19)
    result_start = get_game_setting('DICE_RESULT_TIME', 51)
    data['is_rolling'] = (rolling_start <= timer < result_start)
    
    return Response(data)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def dice_mode(request):
    """Get or set dice mode (manual/random)"""
    if request.method == 'GET':
        mode = get_dice_mode()
        logger.info(f"Admin {request.user.username} fetched dice mode: {mode}")
        return Response({'mode': mode})
    else:
        mode = request.data.get('mode')
        logger.info(f"Admin {request.user.username} setting dice mode to: {mode}")
        if set_dice_mode(mode):
            logger.info(f"Dice mode updated successfully to: {mode}")
            return Response({'mode': mode, 'message': f'Dice mode set to {mode}'})
        logger.warning(f"Admin {request.user.username} provided invalid dice mode: {mode}")
        return Response({'error': 'Invalid mode. Use "manual" or "random"'}, status=status.HTTP_400_BAD_REQUEST)


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

    New Rules:
    - Any number appearing 2+ times is a winner
    - Payout multiplier = frequency (number of occurrences)
    - Example: If number appears 3 times, multiplier is 3 (bet 100 → get 300 total return)
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
        # Payout multiplier = frequency (number of occurrences)
        # Example: frequency 2 → multiplier 2, frequency 3 → multiplier 3, etc.
        payout_multiplier = Decimal(str(frequency))
        
        # Get all bets on this winning number
        winning_bets = Bet.objects.filter(round=round_obj, number=winning_number)
        
        for bet in winning_bets:
            # Safeguard: Skip if already processed to prevent duplicate payouts
            if bet.is_winner:
                continue
                
            # Calculate total payout: bet_amount * multiplier
            total_payout_amount = bet.chip_amount * payout_multiplier
            
            # Store the total payout amount in bet.payout_amount for reference
            bet.payout_amount = total_payout_amount
            bet.is_winner = True
            bet.save()

            # Add 100% to winner's wallet
            wallet = bet.user.wallet
            balance_before = wallet.balance
            wallet.add(total_payout_amount)
            balance_after = wallet.balance

            # Update Redis balance for winner (CRITICAL for Redis-First betting)
            if redis_client:
                try:
                    balance_key = f"user_balance:{bet.user.id}"
                    # Use set instead of incrbyfloat to ensure absolute sync with DB
                    redis_client.set(balance_key, str(wallet.balance), ex=3600)
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
        download_url = get_game_setting('APP_DOWNLOAD_URL', 'https://gunduata.online/download/')
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
@authentication_classes([])
@permission_classes([AllowAny])
@csrf_exempt
def winning_results(request, round_id=None):
    """
    Get winning results for a specific round.
    Returns: All winning bets, statistics, and winning numbers with frequencies.
    """
    from collections import Counter
    from django.db.models import Sum

    # Validate round_id - if it's empty, whitespace, or just a tab, treat as None
    if round_id:
        round_id = round_id.strip()
        if not round_id or len(round_id) == 0:
            round_id = None

    # Get round by ID or use latest completed round
    if round_id:
        try:
            round_obj = GameRound.objects.get(round_id=round_id)
        except GameRound.DoesNotExist:
            return Response({
                'error': 'Round not found',
                'round_id': round_id,
                'message': f'Round {round_id} does not exist in the database'
            }, status=status.HTTP_404_NOT_FOUND)
    else:
        # Get the most recently COMPLETED round with dice results
        round_obj = GameRound.objects.filter(
            status__in=['RESULT', 'COMPLETED'],
            dice_result__isnull=False
        ).order_by('-end_time').first()

        if not round_obj:
            return Response({
                'error': 'No completed round results found',
                'message': 'No completed rounds with dice results available yet.'
            }, status=status.HTTP_404_NOT_FOUND)
    
    # Get user's bets for this round if authenticated
    bets_data = []
    user_total_bet_amount = Decimal('0.00')
    user_total_payout = Decimal('0.00')
    user_winning_bets = 0
    user_losing_bets = 0
    wallet_balance = "0.00"

    if request.user.is_authenticated:
        user_bets = Bet.objects.filter(user=request.user, round=round_obj).order_by('created_at')
        for bet in user_bets:
            user_total_bet_amount += bet.chip_amount
            payout = bet.payout_amount or Decimal('0.00')
            user_total_payout += payout
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

    user_net_result = user_total_payout - user_total_bet_amount
    net_result_str = "{:+.2f}".format(float(user_net_result))

    response_data = {
        "round": {
            "round_id": round_obj.round_id,
            "status": round_obj.status,
            "dice_result": int(round_obj.dice_result) if round_obj.dice_result and str(round_obj.dice_result).isdigit() else round_obj.dice_result,
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
            "total_bets": len(bets_data),
            "total_bet_amount": "{:.2f}".format(float(user_total_bet_amount)),
            "total_payout": "{:.2f}".format(float(user_total_payout)),
            "net_result": "{:.2f}".format(float(user_net_result)),
            "winning_bets": user_winning_bets,
            "losing_bets": user_losing_bets
        },
        "wallet_balance": wallet_balance
    }

    return Response(response_data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def game_stats(request):
    """Admin: Get game statistics"""
    logger.info(f"Admin {request.user.username} fetching game statistics")
    # Get current round
    current_round_obj = None
    if redis_client:
        try:
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
        'dice_mode': get_dice_mode(),
    }

    return Response(stats)


@api_view(['GET'])
@authentication_classes([])  # Disable authentication
@permission_classes([AllowAny])  # Public endpoint - no authentication required
def game_settings_api(request):
    """API endpoint to get current game settings (public)"""
    logger.info("Public settings API access")
    from .utils import get_game_setting
    
    # Get values from DB with correct defaults matching the engine
    betting_close_time = int(get_game_setting('BETTING_CLOSE_TIME', 30))
    dice_roll_time = int(get_game_setting('DICE_ROLL_TIME', 35))
    dice_result_time = int(get_game_setting('DICE_RESULT_TIME', 45))
    round_end_time = int(get_game_setting('ROUND_END_TIME', 70))
    
    settings_data = {
        'BETTING_DURATION': betting_close_time,
        'RESULT_SELECTION_DURATION': dice_roll_time - betting_close_time,
        'RESULT_DISPLAY_DURATION': dice_result_time - dice_roll_time,
        'TOTAL_ROUND_DURATION': round_end_time,
        'DICE_ROLL_TIME': dice_roll_time,
        'BETTING_CLOSE_TIME': betting_close_time,
        'DICE_RESULT_TIME': dice_result_time,
        'RESULT_ANNOUNCE_TIME': dice_result_time,
        'ROUND_END_TIME': round_end_time,
        'CHIP_VALUES': [10, 50, 100, 500, 1000, 5000],
        'PAYOUT_RATIOS': {
            "1": 1.0,
            "2": 2.0,
            "3": 3.0,
            "4": 4.0,
            "5": 5.0,
            "6": 6.0
        }
    }
    
    return Response(settings_data)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def game_timer_settings(request):
    """Admin: Get or set game timer settings"""
    timer_keys = [
        'BETTING_CLOSE_TIME', 
        'DICE_ROLL_TIME', 
        'DICE_RESULT_TIME', 
        'ROUND_END_TIME'
    ]
    
    if request.method == 'GET':
        settings_data = {}
        for key in timer_keys:
            settings_data[key] = get_game_setting(key)
        return Response(settings_data)
    
    elif request.method == 'POST':
        updated_settings = {}
        for key in timer_keys:
            if key in request.data:
                value = request.data[key]
                try:
                    # Validate as integer
                    int_value = int(value)
                    GameSettings.objects.update_or_create(
                        key=key,
                        defaults={'value': str(int_value)}
                    )
                    updated_settings[key] = int_value
                    
                    # Clear in-memory cache in utils
                    from .utils import _SETTINGS_CACHE
                    if key in _SETTINGS_CACHE:
                        del _SETTINGS_CACHE[key]
                except (ValueError, TypeError):
                    return Response(
                        {'error': f'Invalid value for {key}. Must be an integer.'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        return Response({
            'message': 'Timer settings updated successfully',
            'updated_settings': updated_settings
        })


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
            dice_result_str = "-".join(map(str, dice_values))
            
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

        # If count is not 1, return only the most recent round as a single object
        if count != 1 and results:
            # Add wallet_balance if authenticated
            if request.user.is_authenticated:
                try:
                    results[0]["wallet_balance"] = "{:.2f}".format(float(request.user.wallet.balance))
                except:
                    results[0]["wallet_balance"] = "0.00"
            return Response(results[0])

        # Fallback for count=1 or other cases (though logic above now covers most)
        if results:
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
            'timestamp': last_round.end_time.isoformat() if last_round.end_time else None
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
            results.append({
                'round_id': round_obj.round_id,
                'dice_1': round_obj.dice_1,
                'dice_2': round_obj.dice_2,
                'dice_3': round_obj.dice_3,
                'dice_4': round_obj.dice_4,
                'dice_5': round_obj.dice_5,
                'dice_6': round_obj.dice_6,
                'dice_result': round_obj.dice_result,
                'timestamp': round_obj.end_time.isoformat() if round_obj.end_time else round_obj.start_time.isoformat()
            })

        # Cache in Redis
        if redis_client:
            try:
                redis_client.set(cache_key, json.dumps(results), ex=30)
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
                round_data = redis_client.get('current_round')
                if round_data:
                    round_id = json.loads(round_data).get('round_id')
            except: pass
        
        if not round_id:
            round_obj = GameRound.objects.order_by('-start_time').first()
            if not round_obj:
                return Response({'error': 'No round found'}, status=404)
            round_id = round_obj.round_id

    # 2. Fetch from Redis (RAM)
    if redis_client:
        try:
            pipe = redis_client.pipeline()
            pipe.get(f"round:{round_id}:total_exposure")
            pipe.get(f"round:{round_id}:bet_count")
            pipe.hgetall(f"round:{round_id}:user_exposure")
            # Check if keys exist
            pipe.exists(f"round:{round_id}:total_exposure")
            results = pipe.execute()

            total_exposure = results[0] or "0.00"
            bet_count = results[1] or "0"
            user_exposure_map = results[2] or {}
            
            # If total_exposure is missing, it might just be a new round with no bets yet.
            # We only rebuild from DB if we are SURE the round should have data.
            # For now, let's just return 0 if it doesn't exist, instead of rebuilding from DB
            # which can be slow and might show 0 anyway if worker is lagging.
            
            # Filter for specific user if not staff
            if not (request.user.is_staff or request.user.is_superuser):
                user_id_str = str(request.user.id)
                user_exposure = user_exposure_map.get(user_id_str, "0.00")
                user_exposure_map = {user_id_str: user_exposure}
            else:
                # If staff/admin, the user might want to filter by a specific player_id via query param
                target_player_id = request.query_params.get('player_id')
                if target_player_id:
                    user_exposure = user_exposure_map.get(str(target_player_id), "0.00")
                    user_exposure_map = {str(target_player_id): user_exposure}
                elif len(user_exposure_map) > 1:
                    # If no specific player_id requested and multiple exist, 
                    # just show the first one as requested "show only 1 player id"
                    first_key = next(iter(user_exposure_map))
                    user_exposure_map = {first_key: user_exposure_map[first_key]}

            # Prepare the new exposure list format
            exposure_list_formatted = []
            # We need usernames for the new format. 
            # Since Redis only stores IDs, we'll fetch usernames from DB for the active players.
            user_ids = [int(uid) for uid in user_exposure_map.keys()]
            from accounts.models import User
            users_map = {u.id: u.username for u in User.objects.filter(id__in=user_ids)}
            
            for uid_str, amount in user_exposure_map.items():
                uid_int = int(uid_str)
                exposure_list_formatted.append({
                    "player_id": uid_int,
                    "username": users_map.get(uid_int, f"User {uid_int}"),
                    "exposure_amount": amount
                })

            # Get status from Redis if possible
            status_val = "BETTING"
            try:
                state_json = redis_client.get('current_game_state')
                if state_json:
                    status_val = json.loads(state_json).get('status', 'BETTING')
            except: pass

            return Response({
                'round_id': round_id,
                'status': status_val,
                'total_exposure': total_exposure,
                'total_bets': int(bet_count),
                'unique_players': len(exposure_list_formatted),
                'exposure': exposure_list_formatted
            })
        except Exception as e:
            logger.error(f"Redis exposure fetch failed: {e}", exc_info=True)

    # 3. Fallback to DB (Only if Redis fails)
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def submit_prediction(request):
    """
    Submit a prediction/guess after betting closes.
    Users can tap on a number to predict the result (no money involved).
    Only allowed after betting closes and before result is announced.
    """
    serializer = CreatePredictionSerializer(data=request.data)
    if not serializer.is_valid():
        logger.warning(f"User {request.user.username} provided invalid prediction data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    number = serializer.validated_data['number']
    logger.info(f"Prediction attempt by user {request.user.username} (ID: {request.user.id}): Number {number}")

    # Get current round
    round_obj = None
    timer = 0
    
    if redis_client:
        try:
            round_data = redis_client.get('current_round')
            if round_data:
                round_data = json.loads(round_data)
                timer = int(redis_client.get('round_timer') or '0')
                try:
                    round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                except GameRound.DoesNotExist:
                    pass
        except Exception as e:
            logger.error(f"Redis error in submit_prediction: {e}")
    
    # Fallback to latest round
    if not round_obj:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if not round_obj:
            logger.warning(f"Prediction failed for user {request.user.username}: No active round")
            return Response({'error': 'No active round'}, status=status.HTTP_400_BAD_REQUEST)

    # Calculate timer from start time if Redis not available or timer seems wrong
    if not redis_client or timer == 0:
        timer = calculate_current_timer(round_obj.start_time)
    
    # Check if betting has closed (predictions only allowed after betting closes)
    betting_close_time = get_game_setting('BETTING_CLOSE_TIME', 30)
    dice_result_time = get_game_setting('DICE_RESULT_TIME', 51)
    round_end_time = get_game_setting('ROUND_END_TIME', 80)
    
    # Predictions allowed when:
    # 1. Betting has closed (timer >= betting_close_time) AND
    # 2. Result not yet announced (timer < dice_result_time) AND
    # 3. Round is still active (not completed)
    is_betting_closed = timer >= betting_close_time
    is_before_result = timer < dice_result_time
    is_round_active = round_obj.status in ['CLOSED', 'BETTING', 'RESULT'] and round_obj.status != 'COMPLETED'
    
    # Also check if round is very old
    elapsed_total = (timezone.now() - round_obj.start_time).total_seconds()
    if elapsed_total >= round_end_time:
        logger.warning(f"Prediction failed for user {request.user.username}: Round {round_obj.round_id} has ended")
        return Response({'error': 'Round has ended'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not is_betting_closed:
        logger.warning(f"Prediction failed for user {request.user.username}: Betting still open (Timer: {timer}s)")
        return Response({'error': 'Predictions can only be submitted after betting closes'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not is_before_result or round_obj.status == 'RESULT':
        logger.warning(f"Prediction failed for user {request.user.username}: Result already announced")
        return Response({'error': 'Result already announced. Predictions closed.'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if user already submitted a prediction for this round
    existing_prediction = RoundPrediction.objects.filter(user=request.user, round=round_obj).first()
    if existing_prediction:
        # Update existing prediction
        existing_prediction.number = number
        existing_prediction.is_correct = False  # Reset correctness (will be updated when result is announced)
        existing_prediction.save()
        logger.info(f"Prediction updated: User {request.user.username}, Round {round_obj.round_id}, Num {number}")
        serializer = RoundPredictionSerializer(existing_prediction)
        return Response({
            'message': 'Prediction updated',
            'prediction': serializer.data
        }, status=status.HTTP_200_OK)
    
    # Create new prediction
    try:
        prediction = RoundPrediction.objects.create(
            user=request.user,
            round=round_obj,
            number=number
        )
        logger.info(f"Prediction submitted: User {request.user.username}, Round {round_obj.round_id}, Num {number}")
    except Exception as e:
        logger.exception(f"Unexpected error creating prediction for user {request.user.username}: {e}")
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = RoundPredictionSerializer(prediction)
    return Response({
        'message': 'Prediction submitted successfully',
        'prediction': serializer.data
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def round_predictions(request, round_id=None):
    """
    Get all predictions for a specific round.
    Shows how many users predicted each number.
    
    Query params:
    - round_id: (optional) Specific round ID. If not provided, uses current/latest round.
    """
    logger.info(f"User {request.user.username} fetching predictions for round {round_id or 'current'}")
    
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
                round_data = redis_client.get('current_round')
                if round_data:
                    round_data = json.loads(round_data)
                    try:
                        round_obj = GameRound.objects.get(round_id=round_data['round_id'])
                    except GameRound.DoesNotExist:
                        pass
            except Exception as e:
                logger.error(f"Redis error in round_predictions: {e}")
        
        if not round_obj:
            round_obj = GameRound.objects.order_by('-start_time').first()
        
        if not round_obj:
            logger.warning(f"No rounds found for user {request.user.username}")
            return Response({'error': 'No round found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get all predictions for this round
    predictions = RoundPrediction.objects.filter(round=round_obj).select_related('user').order_by('-created_at')
    
    # Get user's own prediction
    user_prediction = None
    try:
        user_prediction = RoundPrediction.objects.get(user=request.user, round=round_obj)
    except RoundPrediction.DoesNotExist:
        pass
    
    # Serialize predictions
    predictions_data = RoundPredictionSerializer(predictions, many=True).data
    
    # Calculate statistics by number
    from django.db.models import Count
    stats_by_number = []
    for num in range(1, 7):
        number_predictions = predictions.filter(number=num)
        number_count = number_predictions.count()
        number_correct = number_predictions.filter(is_correct=True).count()
        stats_by_number.append({
            'number': num,
            'total_predictions': number_count,
            'correct_predictions': number_correct,
        })
    
    # Calculate overall statistics
    total_predictions = predictions.count()
    total_unique_users = predictions.values('user').distinct().count()
    total_correct = predictions.filter(is_correct=True).count()
    
    logger.info(f"Fetched {total_predictions} predictions for round {round_obj.round_id}")
    
    return Response({
        'round': {
            'round_id': round_obj.round_id,
            'status': round_obj.status,
            'dice_result': round_obj.dice_result,
        },
        'user_prediction': RoundPredictionSerializer(user_prediction).data if user_prediction else None,
        'predictions': predictions_data,
        'statistics': {
            'overall': {
                'total_predictions': total_predictions,
                'total_unique_users': total_unique_users,
                'total_correct': total_correct,
            },
            'by_number': stats_by_number,
        },
        'count': len(predictions_data),
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