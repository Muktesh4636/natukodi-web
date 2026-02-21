from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from django.utils import timezone
from django.conf import settings
from django.db import models, transaction
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from decimal import Decimal
import redis
import json
import logging

logger = logging.getLogger('game')

from .models import GameRound, Bet, DiceResult, GameSettings
from .serializers import GameRoundSerializer, BetSerializer, CreateBetSerializer, DiceResultSerializer
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


@csrf_exempt
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
    return Response(data)


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
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

    # Create or update bet
    try:
        with transaction.atomic():
            bet, created = Bet.objects.get_or_create(
                user=request.user,
                round=round_obj,
                number=number,
                defaults={'chip_amount': chip_amount}
            )

            balance_before = wallet.balance
            if not created:
                # Increment existing bet amount
                bet.chip_amount += chip_amount
                bet.save()

            # Deduct from wallet
            wallet.deduct(chip_amount)
            balance_after = wallet.balance

            # Create transaction for the additional wager
            Transaction.objects.create(
                user=request.user,
                transaction_type='BET',
                amount=chip_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Bet on number {number} in round {round_obj.round_id}"
            )

            # Update round stats
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
    return Response(response_data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@csrf_exempt
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
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

            # Update round stats before deleting bet
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


@csrf_exempt
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


@csrf_exempt
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def betting_history(request):
    """Get user's betting history (all bets, not just current round)"""
    limit = int(request.query_params.get('limit', 50))
    logger.info(f"User {request.user.username} fetching betting history (limit: {limit})")
    
    bets = Bet.objects.filter(user=request.user).select_related('round').order_by('-created_at')[:limit]
    serializer = BetSerializer(bets, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def round_results(request, round_id=None):
    """
    Get user's results for a specific round.
    Returns: user's bets, wins/losses, payouts, and wallet balance.
    """
    logger.info(f"User {request.user.username} fetching results for round {round_id or 'current'}")
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
                logger.error(f"Redis error in round_results: {e}")
        
        if not round_obj:
            round_obj = GameRound.objects.order_by('-start_time').first()
        
        if not round_obj:
            logger.warning(f"No rounds found for user {request.user.username}")
            return Response({'error': 'No round found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get user's bets for this round
    bets = Bet.objects.filter(user=request.user, round=round_obj)
    
    # Calculate summary
    total_bet_amount = sum(bet.chip_amount for bet in bets)
    total_payout = sum(bet.payout_amount for bet in bets if bet.payout_amount)
    net_result = total_payout - total_bet_amount
    winning_bets = [bet for bet in bets if bet.is_winner]
    losing_bets = [bet for bet in bets if not bet.is_winner]
    
    # Get wallet balance
    wallet = request.user.wallet
    
    # Serialize bets
    bets_data = BetSerializer(bets, many=True).data
    
    logger.info(f"Results fetched for user {request.user.username}, Round {round_obj.round_id}: Net {net_result}")
    return Response({
        'round': {
            'round_id': round_obj.round_id,
            'status': round_obj.status,
            'dice_result': round_obj.dice_result,
            'start_time': round_obj.start_time,
            'result_time': round_obj.result_time,
        },
        'bets': bets_data,
        'summary': {
            'total_bets': len(bets),
            'total_bet_amount': str(total_bet_amount),
            'total_payout': str(total_payout),
            'net_result': str(net_result),  # Positive = profit, Negative = loss
            'winning_bets_count': len(winning_bets),
            'losing_bets_count': len(losing_bets),
        },
        'wallet': {
            'balance': str(wallet.balance),
        }
    })


@csrf_exempt
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
    return Response(data)


@csrf_exempt
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


def calculate_payouts(round_obj, dice_result=None, dice_values=None):
    """
    Calculate payouts for all bets in the round based on dice frequency.
    Optimized to use batch processing to minimize database hits.
    """
    from collections import Counter
    from django.db.models import F
    
    # Get dice values from round if not provided
    if dice_values is None:
        dice_values = [
            round_obj.dice_1, round_obj.dice_2, round_obj.dice_3,
            round_obj.dice_4, round_obj.dice_5, round_obj.dice_6
        ]
        # Filter out None values
        dice_values = [d for d in dice_values if d is not None]
    
    if not dice_values or len(dice_values) != 6:
        # Fallback to old logic if dice values not available
        if dice_result:
            if isinstance(dice_result, str):
                winning_numbers = [int(n.strip()) for n in dice_result.split(',') if n.strip().isdigit()]
            else:
                winning_numbers = [int(dice_result)]
                
            game_settings = get_all_game_settings()
            
            # Batch process fallback winning bets
            bets_to_update = []
            transactions_to_create = []
            wallets_to_update = []
            
            # Fetch all winning bets at once
            all_winning_bets = Bet.objects.filter(round=round_obj, number__in=winning_numbers).select_related('user__wallet')
            
            for bet in all_winning_bets:
                win_num = bet.number
                payout_ratio = game_settings.get('PAYOUT_RATIOS', {}).get(win_num, 6.0)
                total_payout_amount = bet.chip_amount * Decimal(str(payout_ratio))
                
                # Prepare bet update
                bet.payout_amount = total_payout_amount
                bet.is_winner = True
                bets_to_update.append(bet)
                
                # Prepare wallet update
                wallet = bet.user.wallet
                balance_before = wallet.balance
                wallet.balance += total_payout_amount
                wallets_to_update.append(wallet)
                
                # Prepare transaction
                transactions_to_create.append(Transaction(
                    user=bet.user,
                    transaction_type='WIN',
                    amount=total_payout_amount,
                    balance_before=balance_before,
                    balance_after=wallet.balance,
                    description=f"Win on number {win_num} in round {round_obj.round_id}. Payout: {total_payout_amount}"
                ))
            
            if bets_to_update:
                with transaction.atomic():
                    Bet.objects.bulk_update(bets_to_update, ['payout_amount', 'is_winner'])
                    for w in wallets_to_update:
                        w.save() # Still one by one because bulk_update on large sets of wallets might be risky with concurrent bets, but better than before
                    Transaction.objects.bulk_create(transactions_to_create)
                    
        return
    
    # NEW LOGIC: Any number appearing 2+ times is a winner
    counts = Counter(dice_values)
    winning_info = {num: Decimal(str(count)) for num, count in counts.items() if count >= 2}
    
    if not winning_info:
        return
    
    winning_numbers = list(winning_info.keys())
    
    # Optimized Batch Processing
    try:
        # Fetch all winning bets with wallets in one query
        bets = Bet.objects.filter(
            round=round_obj, 
            number__in=winning_numbers
        ).select_related('user__wallet')
        
        bets_to_update = []
        transactions_to_create = []
        wallets_to_update = {} # user_id -> wallet object
        
        for bet in bets:
            multiplier = winning_info[bet.number]
            total_payout = bet.chip_amount * multiplier
            
            # Prepare bet update
            bet.payout_amount = total_payout
            bet.is_winner = True
            bets_to_update.append(bet)
            
            # Prepare wallet update
            user_id = bet.user_id
            if user_id not in wallets_to_update:
                wallets_to_update[user_id] = bet.user.wallet
            
            wallet = wallets_to_update[user_id]
            balance_before = wallet.balance
            wallet.balance += total_payout
            balance_after = wallet.balance
            
            # Prepare transaction
            transactions_to_create.append(Transaction(
                user=bet.user,
                transaction_type='WIN',
                amount=total_payout,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Win on number {bet.number} ({counts[bet.number]}x) in round {round_obj.round_id}. Payout: {total_payout}"
            ))
            
        if bets_to_update:
            with transaction.atomic():
                # Perform batch updates
                Bet.objects.bulk_update(bets_to_update, ['payout_amount', 'is_winner'])
                Transaction.objects.bulk_create(transactions_to_create)
                # Save wallets - unfortunately Django doesn't have a clean bulk_update for different amounts easily without complex F expressions
                # but we've reduced the number of saves to one per user
                for wallet in wallets_to_update.values():
                    wallet.save()
                    
            logger.info(f"Processed payouts for round {round_obj.round_id}: {len(bets_to_update)} winning bets.")
            
    except Exception as e:
        logger.exception(f"Error calculating payouts for round {round_obj.round_id}: {e}")


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
            # Check if any rounds exist at all
            total_rounds = GameRound.objects.count()
            return Response({
                'error': 'No round found',
                'total_rounds_in_db': total_rounds,
                'message': 'No active or completed rounds available. Please wait for a round to complete.'
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
    
    winning_numbers_info = []
    if dice_values and len(dice_values) == 6:
        counts = Counter(dice_values)
        # Find ALL winning numbers (appearing 2+ times)
        winning_numbers = sorted([num for num, count in counts.items() if count >= 2])
        
        # Process each winning number
        for winning_number in winning_numbers:
            frequency = counts[winning_number]
            number_bets = winning_bets_query.filter(number=winning_number)
            number_total_bets = number_bets.count()
            number_total_payout = number_bets.aggregate(Sum('payout_amount'))['payout_amount__sum'] or Decimal('0.00')
            number_total_bet_amount = number_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or Decimal('0.00')
            
            winning_numbers_info.append({
                'number': winning_number,
                'frequency': frequency,
                'payout_multiplier': float(frequency),
                'total_bets': number_total_bets,
                'total_bet_amount': str(number_total_bet_amount),
                'total_payout': str(number_total_payout),
            })
    
    # Get all winning bets with user info (sorted by payout amount descending)
    winning_bets = winning_bets_query.order_by('-payout_amount')[:limit]
    
    # Serialize winning bets
    winning_bets_data = []
    for bet in winning_bets:
        winning_bets_data.append({
            'id': bet.id,
            'user': {
                'id': bet.user.id,
                'username': bet.user.username,
            },
            'number': bet.number,
            'chip_amount': str(bet.chip_amount),
            'payout_amount': str(bet.payout_amount),
            'created_at': bet.created_at.isoformat(),
        })
    
    # Calculate aggregate statistics
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
        'winning_bets': winning_bets_data,
        'statistics': {
            'total_bets': total_bets,
            'total_bet_amount': str(total_bet_amount),
            'total_winners': total_winners,
            'total_winning_bets_amount': str(total_winning_bets_amount),
            'total_payouts': str(total_payouts),
            'win_rate': round(float(total_winners / total_bets * 100), 2) if total_bets > 0 else 0,
        },
    })


@csrf_exempt
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
@authentication_classes([])  # Disable authentication
@permission_classes([AllowAny])  # Public endpoint - no authentication required
def last_round_results(request):
    """
    API endpoint to get the last completed round results.
    Returns: round_id and all 6 dice results (dice_1 through dice_6).
    """
    logger.info("Public last round results API access")
    # Get the last completed round (status is 'RESULT' or 'COMPLETED')
    last_round = GameRound.objects.filter(
        status__in=['RESULT', 'COMPLETED']
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
    }
    
    return Response(result)


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