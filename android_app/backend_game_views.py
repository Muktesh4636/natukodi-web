from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from decimal import Decimal
import redis
import json
import logging

logger = logging.getLogger('game')

from .models import GameRound, Bet, DiceResult, GameSettings, RoundPrediction
from .serializers import (
    GameRoundSerializer, BetSerializer, CreateBetSerializer, DiceResultSerializer,
    RoundPredictionSerializer, CreatePredictionSerializer
)
from .utils import get_game_setting, get_all_game_settings, calculate_current_timer
from accounts.models import Wallet, Transaction

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
def current_round(request):
    """Get current game round status"""
    logger.info(f"User {request.user.username} (ID: {request.user.id}) fetching current round")
    # Get current round from Redis or database
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
                    # Return data directly from Redis if available, instead of querying DB
                    # This is a major optimization for high load
                    timer = 0
                    try:
                        redis_timer = redis_client.get('round_timer')
                        if redis_timer:
                            timer = int(redis_timer)
                    except Exception:
                        pass
                        
                    if timer <= 0:
                        # Calculate from start_time in round_data
                        try:
                            start_time = datetime.fromisoformat(round_data['start_time'])
                            if timezone.is_aware(timezone.now()) and not timezone.is_aware(start_time):
                                start_time = timezone.make_aware(start_time)
                            timer = max(0, int(round_data.get('round_end_seconds', 80) - (timezone.now() - start_time).total_seconds()))
                        except:
                            timer = 0

                    # Add is_rolling flag
                    rolling_start = get_game_setting('DICE_ROLL_TIME', 19)
                    result_start = get_game_setting('DICE_RESULT_TIME', 51)
                    
                    # Fetch real-time totals from Redis
                    total_bets = 0
                    total_amount = "0.00"
                    try:
                        total_bets_val = redis_client.get(f"round_total_bets:{round_data['round_id']}")
                        if total_bets_val:
                            total_bets = int(total_bets_val)
                        
                        total_amount_val = redis_client.get(f"round_total_amount:{round_data['round_id']}")
                        if total_amount_val:
                            total_amount = "{:.2f}".format(float(total_amount_val))
                    except Exception as redis_err:
                        logger.error(f"Error fetching totals from Redis in current_round: {redis_err}")

                    response_data = {
                        'round_id': round_data['round_id'],
                        'status': round_data['status'],
                        'start_time': round_data['start_time'],
                        'timer': timer,
                        'is_rolling': (rolling_start <= timer < result_start),
                        'dice_result': round_data.get('dice_result'),
                        'dice_1': round_data.get('dice_1'),
                        'dice_2': round_data.get('dice_2'),
                        'dice_3': round_data.get('dice_3'),
                        'dice_4': round_data.get('dice_4'),
                        'dice_5': round_data.get('dice_5'),
                        'dice_6': round_data.get('dice_6'),
                        'total_bets': total_bets,
                        'total_amount': total_amount,
                    }
                    return Response(response_data)
        except Exception as e:
            logger.error(f"Redis error in current_round: {e}")
    
    # Fallback to database if Redis fails or data not found
    # ... rest of the function ...
    
    # Fallback to latest round or create new one
    if not round_obj:
        round_obj = GameRound.objects.order_by('-start_time').first()
        
        round_end_time = get_game_setting('ROUND_END_TIME', 80)
        # Check if we need to create a new round
        should_create_new = False
        if not round_obj:
            should_create_new = True
            logger.info("No existing rounds found, creating new one")
        else:
            elapsed = (timezone.now() - round_obj.start_time).total_seconds()
            if round_obj.status == 'COMPLETED':
                should_create_new = True
                logger.info(f"Round {round_obj.round_id} is completed, creating new one")
            elif round_obj.status in ['RESULT', 'CLOSED']:
                # Check if round is old (past ROUND_END_TIME seconds) - create new round
                if elapsed >= round_end_time:
                    should_create_new = True
                    logger.info(f"Round {round_obj.round_id} is stale (Status: {round_obj.status}), creating new one")
            elif elapsed >= round_end_time:
                # Round is stale even if status wasn't updated (e.g., still BETTING/WAITING)
                should_create_new = True
                logger.info(f"Round {round_obj.round_id} is stale (Elapsed: {elapsed}s), creating new one")
        
        if should_create_new:
            # Mark old round as completed if it exists
            if round_obj and round_obj.status != 'COMPLETED':
                round_obj.status = 'COMPLETED'
                round_obj.end_time = timezone.now()
                round_obj.save()
                logger.info(f"Marked round {round_obj.round_id} as completed")
            
            # Create new round
            round_obj = GameRound.objects.create(
                round_id=f"R{int(timezone.now().timestamp())}",
                status='BETTING',
                betting_close_seconds=get_game_setting('BETTING_CLOSE_TIME', 30),
                dice_roll_seconds=get_game_setting('DICE_ROLL_TIME', 7),
                dice_result_seconds=get_game_setting('DICE_RESULT_TIME', 51),
                round_end_seconds=get_game_setting('ROUND_END_TIME', 80)
            )
            logger.info(f"Created new round: {round_obj.round_id}")
        
        # Store in Redis if available (use pipeline for efficient batch writes)
        if redis_client:
            try:
                # Calculate timer from start time
                timer = calculate_current_timer(round_obj.start_time)
                
                round_data = {
                    'round_id': round_obj.round_id,
                    'status': round_obj.status,
                    'start_time': round_obj.start_time.isoformat(),
                    'timer': timer,
                }
                pipe = redis_client.pipeline()
                pipe.set('current_round', json.dumps(round_data))
                pipe.set('round_timer', str(timer))
                pipe.execute()
                logger.info(f"Synced round {round_obj.round_id} to Redis")
            except Exception as e:
                logger.error(f"Failed to sync round to Redis: {e}")
    
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def place_bet(request):
    """Place a bet on a number"""
    serializer = CreateBetSerializer(data=request.data)
    if not serializer.is_valid():
        logger.warning(f"User {request.user.username} provided invalid bet data: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    number = serializer.validated_data['number']
    chip_amount = serializer.validated_data['chip_amount']
    logger.info(f"Bet attempt by user {request.user.username} (ID: {request.user.id}): Number {number}, Amount {chip_amount}")

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
            logger.error(f"Redis error in place_bet: {e}")
    
    # Fallback to latest round
    if not round_obj:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if not round_obj:
            logger.warning(f"Bet failed for user {request.user.username}: No active round")
            return Response({'error': 'No active round'}, status=status.HTTP_400_BAD_REQUEST)

    # Calculate timer from start time if Redis not available or timer seems wrong
    if not redis_client or timer == 0:
        timer = calculate_current_timer(round_obj.start_time)
    
    # Check if betting is open based on timer AND status
    betting_close_time = get_game_setting('BETTING_CLOSE_TIME', 30)
    round_end_time = get_game_setting('ROUND_END_TIME', 80)
    
    # Allow betting if:
    # 1. Timer is within betting window (0-30s) AND
    # 2. Round status is BETTING OR (round is new and timer < 30)
    is_within_betting_window = timer < betting_close_time
    is_round_active = round_obj.status in ['BETTING', 'WAITING'] or (round_obj.status == 'RESULT' and timer < betting_close_time)
    
    # Also check if round is very old (past 60s) - should create new round
    elapsed_total = (timezone.now() - round_obj.start_time).total_seconds()
    if elapsed_total >= round_end_time:
        logger.warning(f"Bet failed for user {request.user.username}: Round {round_obj.round_id} has ended")
        return Response({'error': 'Round has ended. Please refresh to see the new round.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not is_within_betting_window or not is_round_active:
        if timer >= betting_close_time:
            logger.warning(f"Bet failed for user {request.user.username}: Betting period ended (Timer: {timer}s, Limit: {betting_close_time}s)")
            return Response({'error': f'Betting period has ended. Betting closes at {betting_close_time} seconds.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.warning(f"Bet failed for user {request.user.username}: Round {round_obj.round_id} status is {round_obj.status}")
            return Response({'error': 'Betting is closed'}, status=status.HTTP_400_BAD_REQUEST)

    # Get user wallet
    try:
        wallet = Wallet.objects.get(user=request.user)
    except Wallet.DoesNotExist:
        logger.error(f"Wallet not found for user {request.user.username}")
        return Response({'error': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)

    # Check balance
    if wallet.balance < chip_amount:
        logger.warning(f"Bet failed for user {request.user.username}: Insufficient balance (Balance: {wallet.balance}, Requested: {chip_amount})")
        return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

    # Create bet (allow multiple bets on same number)
    try:
        with transaction.atomic():
            # Always create a new bet - no accumulation
            bet = Bet.objects.create(
                user=request.user,
                round=round_obj,
                number=number,
                chip_amount=chip_amount
            )

            balance_before = wallet.balance
            # Deduct from wallet
            wallet.deduct(chip_amount)
            balance_after = wallet.balance

            # Create transaction for the wager
            Transaction.objects.create(
                user=request.user,
                transaction_type='BET',
                amount=chip_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Bet on number {number} in round {round_obj.round_id}"
            )

            # Update round stats in Redis for high performance and to avoid DB row contention
            if redis_client:
                try:
                    redis_client.incr(f"round_total_bets:{round_obj.round_id}")
                    # Redis incrbyfloat handles decimal-like strings
                    redis_client.incrbyfloat(f"round_total_amount:{round_obj.round_id}", float(chip_amount))
                    
                    # Also update the local object so the response is correct, 
                    # but we don't save it to DB here anymore
                    round_obj.total_bets += 1
                    round_obj.total_amount += chip_amount
                except Exception as redis_err:
                    logger.error(f"Redis error updating round stats: {redis_err}")
                    # Fallback to DB update if Redis fails
                    round_obj.total_bets += 1
                    round_obj.total_amount += chip_amount
                    round_obj.save()
            else:
                # Fallback to DB update if Redis not available
                round_obj.total_bets += 1
                round_obj.total_amount += chip_amount
                round_obj.save()

            logger.info(f"Bet placed successfully: User {request.user.username}, Round {round_obj.round_id}, Num {number}, Amount {chip_amount}")
    except Exception as e:
        logger.exception(f"Unexpected error placing bet for user {request.user.username}: {e}")
        return Response({'error': 'Internal server error during betting'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = BetSerializer(bet)
    response_data = {
        'bet': serializer.data,
        'wallet_balance': str(wallet.balance),
        'round': {
            'round_id': round_obj.round_id,
            'total_bets': round_obj.total_bets,
            'total_amount': str(round_obj.total_amount)
        }
    }
    return Response(response_data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def remove_bet(request, number):
    """Remove a bet for a specific number"""
    logger.info(f"Remove bet request by user {request.user.username} (ID: {request.user.id}) for number {number}")
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
            logger.error(f"Redis error in remove_bet: {e}")
    
    # Fallback to latest round
    if not round_obj:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if not round_obj:
            logger.warning(f"Remove bet failed for user {request.user.username}: No active round")
            return Response({'error': 'No active round'}, status=status.HTTP_400_BAD_REQUEST)

    # Calculate timer from start time if Redis not available or timer seems wrong
    if not redis_client or timer == 0:
        timer = calculate_current_timer(round_obj.start_time)
    
    # Check if betting is open based on timer AND status
    betting_close_time = get_game_setting('BETTING_CLOSE_TIME', 30)
    round_end_time = get_game_setting('ROUND_END_TIME', 80)
    
    # Allow betting if:
    # 1. Timer is within betting window (0-30s) AND
    # 2. Round status is BETTING OR (round is new and timer < 30)
    is_within_betting_window = timer < betting_close_time
    is_round_active = round_obj.status in ['BETTING', 'WAITING'] or (round_obj.status == 'RESULT' and timer < betting_close_time)
    
    # Also check if round is very old (past 60s) - should create new round
    elapsed_total = (timezone.now() - round_obj.start_time).total_seconds()
    if elapsed_total >= round_end_time:
        logger.warning(f"Remove bet failed for user {request.user.username}: Round {round_obj.round_id} has ended")
        return Response({'error': 'Round has ended. Please refresh to see the new round.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not is_within_betting_window or not is_round_active:
        if timer >= betting_close_time:
            logger.warning(f"Remove bet failed for user {request.user.username}: Betting period ended (Timer: {timer}s, Limit: {betting_close_time}s)")
            return Response({'error': f'Betting period has ended. Betting closes at {betting_close_time} seconds.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.warning(f"Remove bet failed for user {request.user.username}: Betting is closed (Status: {round_obj.status})")
            return Response({'error': 'Betting is closed'}, status=status.HTTP_400_BAD_REQUEST)

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
                    # Decrement totals in Redis
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
                    logger.error(f"Redis error updating round stats: {redis_err}")
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
            logger.error(f"Redis error in remove_last_bet: {e}")
    
    # Fallback to latest round
    if not round_obj:
        round_obj = GameRound.objects.order_by('-start_time').first()
        if not round_obj:
            logger.warning(f"Last bet request failed for user {request.user.username}: No active round")
            return Response({'error': 'No active round'}, status=status.HTTP_400_BAD_REQUEST)

    # Get the user's last (most recent) bet for this round
    try:
        bet = Bet.objects.filter(user=request.user, round=round_obj).order_by('-created_at').first()
        if not bet:
            logger.warning(f"Last bet request failed for user {request.user.username}: No bets found in round {round_obj.round_id}")
            return Response({'error': 'No bets found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception(f"Error finding last bet for user {request.user.username}: {e}")
        return Response({'error': 'Error finding last bet'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # If it's a GET request, just return the bet details
    if request.method == 'GET':
        return Response({
            'bet': {
                'id': bet.id,
                'number': bet.number,
                'chip_amount': str(bet.chip_amount),
                'created_at': bet.created_at,
                'is_winner': bet.is_winner,
                'payout_amount': str(bet.payout_amount) if bet.payout_amount else None
            },
            'round': {
                'round_id': round_obj.round_id,
                'status': round_obj.status
            }
        })

    # If it's a DELETE request, proceed with removal
    # Calculate timer from start time if Redis not available or timer seems wrong
    if not redis_client or timer == 0:
        timer = calculate_current_timer(round_obj.start_time)
    
    # Check if betting is open based on timer AND status
    betting_close_time = get_game_setting('BETTING_CLOSE_TIME', 30)
    round_end_time = get_game_setting('ROUND_END_TIME', 80)
    
    is_within_betting_window = timer < betting_close_time
    is_round_active = round_obj.status in ['BETTING', 'WAITING'] or (round_obj.status == 'RESULT' and timer < betting_close_time)
    
    elapsed_total = (timezone.now() - round_obj.start_time).total_seconds()
    if elapsed_total >= round_end_time:
        logger.warning(f"Remove last bet failed for user {request.user.username}: Round {round_obj.round_id} has ended")
        return Response({'error': 'Round has ended. Please refresh to see the new round.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not is_within_betting_window or not is_round_active:
        if timer >= betting_close_time:
            logger.warning(f"Remove last bet failed for user {request.user.username}: Betting period ended (Timer: {timer}s, Limit: {betting_close_time}s)")
            return Response({'error': f'Betting period has ended. Betting closes at {betting_close_time} seconds.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.warning(f"Remove last bet failed for user {request.user.username}: Betting is closed (Status: {round_obj.status})")
            return Response({'error': 'Betting is closed'}, status=status.HTTP_400_BAD_REQUEST)

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
                    logger.error(f"Redis error updating round stats: {redis_err}")
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
@permission_classes([IsAuthenticated])
def winning_results(request, round_id=None):
    """
    Get winning results for a specific round.
    Returns: All winning bets, statistics, and winning numbers with frequencies.

    Query params:
    - round_id: (optional) Specific round ID. If not provided, uses current/latest round.
    - limit: (optional) Limit number of winning bets returned (default: 100)
    - top_winners: (optional) If true, returns only top winners by payout amount
    """
    from collections import Counter
    from django.db.models import Sum

    # Validate round_id - if it's empty, whitespace, or just a tab, treat as None
    if round_id:
        round_id = round_id.strip()
        if not round_id or len(round_id) == 0:
            round_id = None

    # Get round by ID or use current round
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
        # Get the most recently COMPLETED round with dice results (for "last round results")
        round_obj = GameRound.objects.filter(
            status='COMPLETED',
            dice_result__isnull=False
        ).order_by('-end_time').first()

        if not round_obj:
            # If no completed rounds with results, check if any rounds exist at all
            total_rounds = GameRound.objects.count()
            completed_rounds = GameRound.objects.filter(status='COMPLETED').count()
            return Response({
                'error': 'No completed round results found',
                'total_rounds_in_db': total_rounds,
                'completed_rounds': completed_rounds,
                'message': 'No completed rounds with dice results available yet. Please wait for a round to complete.'
            }, status=status.HTTP_404_NOT_FOUND)
    
    # Get query parameters
    limit = int(request.query_params.get('limit', 100))
    top_winners = request.query_params.get('top_winners', 'false').lower() == 'true'
    
    # Get all winning bets for this round
    winning_bets_query = Bet.objects.filter(round=round_obj, is_winner=True).select_related('user')
    
    # Get dice values and calculate frequencies
    dice_values = [
        round_obj.dice_1, round_obj.dice_2, round_obj.dice_3,
        round_obj.dice_4, round_obj.dice_5, round_obj.dice_6
    ]
    # Filter out None values but keep all valid dice values (1-6)
    dice_values = [d for d in dice_values if d is not None and 1 <= d <= 6]
    
    # Get all winning numbers and frequencies
    winning_numbers_info = []
    if dice_values and len(dice_values) == 6:
        counts = Counter(dice_values)
        # Find ALL winning numbers (appearing 2+ times)
        winning_numbers = sorted([num for num, count in counts.items() if count >= 2])
        
        # Process each winning number
        for winning_number in winning_numbers:
            frequency = counts[winning_number]
            # No longer fetching individual winning bets for winning_numbers_info
            
            winning_numbers_info.append({
                'number': winning_number,
                'frequency': frequency,
                'payout_multiplier': float(frequency),
            })
    
    # Aggregate statistics
    total_winners = winning_bets_query.count()
    total_winning_bets_amount = winning_bets_query.aggregate(Sum('chip_amount'))['chip_amount__sum'] or Decimal('0.00')
    total_payouts = winning_bets_query.aggregate(Sum('payout_amount'))['payout_amount__sum'] or Decimal('0.00')
    
    # Get all bets for comparison
    all_bets = Bet.objects.filter(round=round_obj)
    total_bets = all_bets.count()
    total_bet_amount = all_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or Decimal('0.00')
    
    return Response({
        'round_id': round_obj.round_id,  # Current round ID (prominent)
        'dice_result': round_obj.dice_result,  # Current round result (prominent)
        'round': {
            'round_id': round_obj.round_id,
            'status': round_obj.status,
            'dice_result': round_obj.dice_result,
            'dice_values': dice_values if dice_values and len(dice_values) == 6 else None,
            'start_time': round_obj.start_time.isoformat(),
            'result_time': round_obj.result_time.isoformat() if round_obj.result_time else None,
            'end_time': round_obj.end_time.isoformat() if round_obj.end_time else None,
        },
        'winning_numbers': winning_numbers_info,
        'winning_bets': [], # Removed individual winning bets for privacy/performance
        'statistics': {
            'total_bets': total_bets,
            'total_bet_amount': str(total_bet_amount),
            'total_winners': total_winners,
            'total_winning_bets_amount': str(total_winning_bets_amount),
            'total_payouts': str(total_payouts),
            'win_rate': round(float(total_winners / total_bets * 100), 2) if total_bets > 0 else 0,
        },
    })


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
    
    settings_data = {
        'betting_close_time': get_game_setting('BETTING_CLOSE_TIME', 30),
        'dice_result_time': get_game_setting('DICE_RESULT_TIME', 51),
        'round_end_time': get_game_setting('ROUND_END_TIME', 70),
    }
    
    return Response(settings_data)


@api_view(['GET'])
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
        last_round = GameRound.objects.filter(
            status__in=['RESULT', 'COMPLETED'],
            dice_result__isnull=False
        ).order_by('-end_time').first()

        if not last_round:
            # Try order by start_time if end_time is null
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
def round_exposure(request, round_id=None):
    """
    Get total exposure (total bet amount) for each player in a specific round.
    
    Query params:
    - round_id: (optional) Specific round ID. If not provided, uses current/latest round.
    - user_id: (optional) Filter by specific user ID.
    """
    # Get round by ID or use current round
    if round_id:
        try:
            round_obj = GameRound.objects.get(round_id=round_id)
        except GameRound.DoesNotExist:
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
            except Exception:
                pass
        
        if not round_obj:
            round_obj = GameRound.objects.order_by('-start_time').first()
        
        if not round_obj:
            return Response({'error': 'No round found'}, status=status.HTTP_404_NOT_FOUND)

    # Build query
    bets_query = Bet.objects.filter(round=round_obj)
    
    # Check if user is admin
    is_admin = request.user.is_staff or request.user.is_superuser
    
    # Support filtering by user_id via query param (admin only)
    user_id_param = request.query_params.get('user_id')
    if user_id_param:
        if is_admin:
            try:
                bets_query = bets_query.filter(user_id=int(user_id_param))
            except ValueError:
                return Response({'error': 'Invalid user_id'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(
                {'error': 'Only admins can filter by user_id'}, 
                status=status.HTTP_403_FORBIDDEN
            )
    elif not is_admin:
        # Non-admin users can only see their own exposure
        bets_query = bets_query.filter(user=request.user)

    # Aggregate exposure by user
    from django.db.models import Sum, Count
    exposure_data = bets_query.values('user_id', 'user__username').annotate(
        exposure_amount=Sum('chip_amount'),
        bet_count=Count('id')
    ).order_by('-exposure_amount')

    # Format response
    results = []
    total_exposure = Decimal('0.00')
    for entry in exposure_data:
        exposure_amt = entry['exposure_amount'] or Decimal('0.00')
        total_exposure += exposure_amt
        results.append({
            'player_id': entry['user_id'],
            'username': entry['user__username'],
            'exposure_amount': str(exposure_amt),
            'bet_count': entry['bet_count']
        })

    # Calculate overall statistics (only for filtered bets if non-admin)
    stats_bets_query = bets_query  # Use the same filtered query
    overall_stats = stats_bets_query.aggregate(
        total_bets=Count('id'),
        total_amount=Sum('chip_amount'),
        total_unique_players=Count('user_id', distinct=True)
    )

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
            'betting_close_time': round_obj.betting_close_time.isoformat() if round_obj.betting_close_time else None,
            'result_time': round_obj.result_time.isoformat() if round_obj.result_time else None,
            'end_time': round_obj.end_time.isoformat() if round_obj.end_time else None,
        },
        'exposure': results,
        'statistics': {
            'total_exposure': str(total_exposure),
            'total_bets': overall_stats['total_bets'] or 0,
            'total_amount': str(overall_stats['total_amount'] or Decimal('0.00')),
            'total_unique_players': overall_stats['total_unique_players'] or 0,
        }
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