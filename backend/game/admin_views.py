from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from django.db import transaction as db_transaction
import redis
import json
import os
from collections import Counter
from .models import GameRound, Bet, DiceResult, GameSettings, AdminPermissions, WhiteLabelLead
from accounts.models import Wallet, Transaction, DepositRequest, WithdrawRequest, User, PaymentMethod
from accounts.player_distribution import (
    redistribute_all_players,
    balance_player_distribution,
    get_admins_for_distribution
)
from django.db.models import Count, Sum, Q, F, Value
from django.db.models.functions import Coalesce
try:
    from accounts.models import AdminProfile
except ImportError:
    AdminProfile = None
from .views import get_dice_mode, set_dice_mode
from .admin_utils import (
    is_super_admin, is_admin, has_permission, get_admin_profile,
    super_admin_required, admin_required, permission_required,
    get_admin_permissions, has_menu_permission, invalidate_admin_permissions_cache,
)
from .utils import get_game_setting, clear_game_setting_cache
from .load_test_utils import load_tester
from decimal import Decimal, InvalidOperation
import decimal
from django.core.paginator import Paginator
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

# Cache TTLs for admin dashboard (reduce DB load and avoid 504 timeouts)
ADMIN_DASHBOARD_STATS_CACHE_KEY = 'admin_dashboard_bet_stats'
ADMIN_DASHBOARD_STATS_TTL = 15  # seconds
ADMIN_DASHBOARD_DATA_CACHE_KEY = 'admin_dashboard_data_json'
ADMIN_DASHBOARD_DATA_TTL = 4   # seconds (polling every 5s)

# Redis connection using connection pool (optimized for scalability)
from .utils import get_redis_client

# Redis connection with tiered failover
redis_client = get_redis_client()

def get_admin_context(request, extra_context=None):
    """Helper function to get common admin context for all admin pages"""
    admin_permissions = get_admin_permissions(request.user)
    # For super admins, create a dummy object with all permissions set to True for template
    if is_super_admin(request.user) and admin_permissions is None:
        class DummyPermissions:
            can_view_dashboard = True
            can_control_dice = True
            can_view_recent_rounds = True
            can_view_all_bets = True
            can_view_wallets = True
            can_view_players = True
            can_view_deposit_requests = True
            can_view_withdraw_requests = True
            can_view_transactions = True
            can_view_game_settings = True
            can_view_admin_management = True
            can_manage_payment_methods = True
        admin_permissions = DummyPermissions()
    
    context = {
        'admin_permissions': admin_permissions,
        'is_super_admin': is_super_admin(request.user),
        'user': request.user,
    }
    
    if extra_context:
        context.update(extra_context)
    
    return context

@ensure_csrf_cookie
@csrf_exempt
def admin_login(request):
    """Custom login page for game admin panel - SECURITY: Rate limited"""
    if request.user.is_authenticated and is_admin(request.user):
        # Already logged in and is admin, redirect to dashboard
        next_url = request.GET.get('next', '/game-admin/dashboard/')
        return redirect(next_url)
    
    # SECURITY: Rate limiting to prevent brute force attacks
    from django.core.cache import cache
    from django.conf import settings
    
    # Get client IP address
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0].strip()
    else:
        client_ip = request.META.get('REMOTE_ADDR', '')
    
    cache_key = f'login_attempts_{client_ip}'
    failed_logins_key = f'failed_logins_{client_ip}'
    
    # Check rate limit: max 5 attempts per 15 minutes (short-term protection)
    login_attempts = cache.get(cache_key, 0)
    if login_attempts >= 5:
        error_message = 'Too many login attempts. Please try again in 15 minutes.'
        context = {
            'next': request.GET.get('next', '/game-admin/dashboard/'),
            'error_message': error_message,
        }
        return render(request, 'admin/login.html', context)
    
    # Check brute force protection: 50 failed attempts = 2 hour ban (configurable)
    import os
    brute_force_threshold = int(os.getenv('BRUTE_FORCE_THRESHOLD', '50'))
    brute_force_ban_time = int(os.getenv('BRUTE_FORCE_BAN_TIME', '7200'))
    
    failed_logins = cache.get(failed_logins_key, 0)
    if failed_logins >= brute_force_threshold:
        ban_hours = brute_force_ban_time // 3600
        error_message = f'Too many failed login attempts. Your IP has been blocked for {ban_hours} hours.'
        context = {
            'next': request.GET.get('next', '/game-admin/dashboard/'),
            'error_message': error_message,
        }
        return render(request, 'admin/login.html', context)
    
    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        next_url = request.POST.get('next', '/game-admin/dashboard/')
        
        if username and password:
            from django.contrib.auth import authenticate, login
            user = authenticate(request, username=username, password=password)
            if user is not None:
                if is_admin(user):
                    # Successful login - reset all attempt counters
                    cache.delete(cache_key)
                    cache.delete(failed_logins_key)
                    login(request, user)
                    messages.success(request, f'Welcome, {user.username}!')
                    return redirect(next_url)
                else:
                    error_message = 'You do not have permission to access the admin panel.'
                    # Increment failed attempt counter
                    login_attempts = cache.get(cache_key, 0) + 1
                    cache.set(cache_key, login_attempts, 900)  # 15 minutes
                    # Track failed logins for firewall middleware
                    failed_count = cache.get(failed_logins_key, 0) + 1
                    cache.set(failed_logins_key, failed_count, 900)  # 15 minutes
                    
                    # SECURITY: If too many failed attempts, permanently block IP
                    if failed_count >= brute_force_threshold:
                        from dice_game.attack_detection import AttackDetector
                        AttackDetector.block_ip_permanently(client_ip)
                        error_message = 'Too many failed login attempts. Your IP has been permanently blocked.'
            else:
                error_message = 'Invalid username or password.'
                # Increment failed attempt counter
                login_attempts = cache.get(cache_key, 0) + 1
                cache.set(cache_key, login_attempts, 900)  # 15 minutes
                # Track failed logins for firewall middleware
                failed_count = cache.get(failed_logins_key, 0) + 1
                cache.set(failed_logins_key, failed_count, 900)  # 15 minutes
                
                # SECURITY: If too many failed attempts, permanently block IP
                if failed_count >= brute_force_threshold:
                    from dice_game.attack_detection import AttackDetector
                    AttackDetector.block_ip_permanently(client_ip)
                    error_message = 'Too many failed login attempts. Your IP has been permanently blocked.'
        else:
            error_message = 'Please provide both username and password.'
    
    context = {
        'next': request.GET.get('next', '/game-admin/dashboard/'),
        'error_message': error_message,
    }
    return render(request, 'admin/login.html', context)


def admin_logout(request):
    """Logout view for game admin panel"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('admin_login')


@login_required(login_url='/game-admin/login/')
@admin_required
def admin_dashboard(request):
    if not has_menu_permission(request.user, 'dashboard'):
        # If user has no dashboard permission, redirect to the first page they DO have permission for
        if has_menu_permission(request.user, 'deposit_requests'):
            return redirect('deposit_requests')
        elif has_menu_permission(request.user, 'withdraw_requests'):
            return redirect('withdraw_requests')
        elif has_menu_permission(request.user, 'players'):
            return redirect('manage_players')
        elif has_menu_permission(request.user, 'wallets'):
            return redirect('wallets')
        elif has_menu_permission(request.user, 'recent_rounds'):
            return redirect('recent_rounds')
        
        # If no permissions at all, redirect to core admin or logout
        messages.error(request, 'You do not have permission to view the dashboard.')
        return redirect('admin_login')
    
    admin_profile = get_admin_profile(request.user)
    
    # Get current round state using helper
    from .utils import get_current_round_state
    current_round, timer, status, _ = get_current_round_state(redis_client)

    # Dashboard stats with short cache to avoid heavy Bet aggregates on every load (reduces 504 risk)
    bet_stats = cache.get(ADMIN_DASHBOARD_STATS_CACHE_KEY)
    if bet_stats is None:
        bet_stats = Bet.objects.aggregate(
            total_bets=Count('id'),
            total_amount=Sum('chip_amount'),
            total_payout=Sum('payout_amount')
        )
        try:
            cache.set(ADMIN_DASHBOARD_STATS_CACHE_KEY, bet_stats, ADMIN_DASHBOARD_STATS_TTL)
        except Exception:
            pass
    total_bets = bet_stats.get('total_bets') or 0
    total_amount = bet_stats.get('total_amount') or 0
    total_payout = bet_stats.get('total_payout') or 0
    total_profit = total_amount - total_payout

    # Get game timing settings for display (use current round settings if available)
    if current_round:
        betting_close_time = current_round.betting_close_seconds
        dice_result_time = current_round.dice_result_seconds
        round_end_time = current_round.round_end_seconds
    else:
        betting_close_time = get_game_setting('BETTING_CLOSE_TIME', 30)
        dice_result_time = get_game_setting('DICE_RESULT_TIME', 51)
        round_end_time = get_game_setting('ROUND_END_TIME', 80)
    
    context = get_admin_context(request, {
        'current_round': current_round,
        'timer': timer,
        'status': status,
        'total_bets': total_bets,
        'total_amount': total_amount,
        'total_payout': total_payout,
        'total_profit': total_profit,
        'page': 'dashboard',
        'admin_profile': admin_profile,
        'betting_close_time': betting_close_time,
        'dice_result_time': dice_result_time,
        'round_end_time': round_end_time,
    })
    return render(request, 'admin/game_dashboard.html', context)

@admin_required
def set_dice_result_view(request):
    """Admin view to set dice result (1-6)"""
    if not request.session.get('dice_control_verified'):
        messages.error(request, 'Please verify your PIN first.')
        return redirect('dice_control')

    if request.method == 'POST':
        try:
            # Get current round state using helper
            from .utils import get_current_round_state, get_game_setting
            
            # Enforce local fallback for redis_client if global is missing/None
            local_redis = None
            try:
                 local_redis = redis_client
            except NameError:
                 pass
                 
            round_obj, timer, status, _ = get_current_round_state(local_redis)

            # Get dice result time (needed for restriction check and finalization logic)
            dice_result_time = get_game_setting('DICE_RESULT_TIME', 51)
            
            # Check timer: Cannot set result after dice_result_time (51s)
            if timer >= dice_result_time:
                messages.error(request, f'Cannot set dice result after {dice_result_time} seconds. Use Manual Adjust mode to override.')
                return redirect('dice_control')

            if not round_obj:
                messages.error(request, 'No active round')
                return redirect('dice_control')
            
            dice_result = request.POST.get('result')
            if dice_result:
                try:
                    result_value = int(dice_result)
                    if not (1 <= result_value <= 6):
                        messages.error(request, 'Dice result must be between 1 and 6')
                        return redirect('dice_control')
                except ValueError:
                    messages.error(request, 'Invalid dice result value')
                    return redirect('dice_control')

                # Set result on round object
                round_obj.dice_result = str(result_value)
                # For compatibility, set all dice to this value (simplified legacy behavior)
                for i in range(1, 7):
                    setattr(round_obj, f'dice_{i}', result_value)
                
                # Only finalize the round (status, payouts, broadcast) if we are at or past result time
                should_finalize = timer >= dice_result_time
                
                if should_finalize:
                    round_obj.status = 'RESULT'
                    if not round_obj.result_time:
                        round_obj.result_time = timezone.now()
                
                round_obj.save()
                
                # Create or update dice result record
                DiceResult.objects.update_or_create(
                    round=round_obj,
                    defaults={
                        'result': str(result_value),
                        'set_by': request.user
                    }
                )
                
                # Update Redis
                if local_redis:
                    try:
                        # 1. Update legacy current_round key
                        round_data = local_redis.get('current_round')
                        if round_data:
                            round_data = json.loads(round_data)
                            round_data['dice_result'] = str(result_value)
                            # Update all dice values
                            for i in range(1, 7):
                                round_data[f'dice_{i}'] = result_value
                            
                            if should_finalize:
                                round_data['status'] = 'RESULT'
                            
                            local_redis.set('current_round', json.dumps(round_data))
                        
                        # 2. Update manual_dice_result for the engine to pick up
                        # Format: "1,1,1,1,1,1"
                        manual_dice_str = ",".join([str(result_value)] * 6)
                        local_redis.set("manual_dice_result", manual_dice_str, ex=300)
                    except Exception:
                        pass
                
                # ONLY calculate payouts and broadcast if finalizing
                if should_finalize:
                    # Calculate payouts
                    from .views import calculate_payouts
                    # Legacy mode: all dice same
                    dice_values = [result_value] * 6
                    calculate_payouts(round_obj, dice_result=str(result_value), dice_values=dice_values)
                    
                    # Broadcast to WebSocket
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        try:
                            async_to_sync(channel_layer.group_send)(
                                'game_room',
                                {
                                    'type': 'dice_result',
                                    'result': str(result_value),
                                    'dice_values': dice_values,
                                    'round_id': round_obj.round_id,
                                }
                            )
                        except Exception:
                            pass
                
                mode_text = " (Pre-set)" if not should_finalize else ""
                messages.success(request, f'Dice result set{mode_text}: {result_value}')
            else:
                messages.error(request, 'Dice result is required')

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            from django.http import HttpResponse
            return HttpResponse(f"<html><body><h1>Error setting dice result</h1><pre>{error_trace}</pre><br><a href='/game-admin/dice-control/'>Back to Dice Control</a></body></html>")
            
    referer = request.META.get('HTTP_REFERER', '')
    if 'dice-control' in referer:
        return redirect('dice_control')
    return redirect('admin_dashboard')

@admin_required
def toggle_dice_mode(request):
    """Toggle dice mode between manual and random"""
    if not request.session.get('dice_control_verified'):
        messages.error(request, 'Please verify your PIN first.')
        return redirect('dice_control')

    if request.method == 'POST':
        current_mode = get_dice_mode()
        new_mode = 'manual' if current_mode == 'random' else 'random'
        set_dice_mode(new_mode)
        messages.success(request, f'Dice mode changed to {new_mode}')
    referer = request.META.get('HTTP_REFERER', '')
    if 'dice-control' in referer:
        return redirect('dice_control')
    return redirect('admin_dashboard')

@admin_required
def admin_dashboard_data(request):
    """API endpoint to get admin dashboard data without page reload. Cached briefly to avoid 504 timeouts."""
    # Serve from cache when possible (polling hits this every 5s; cache 4s reduces DB/Redis load)
    cached = cache.get(ADMIN_DASHBOARD_DATA_CACHE_KEY)
    if cached is not None:
        from django.http import HttpResponse
        return HttpResponse(cached, content_type='application/json')

    # Get current round state using helper
    from .utils import get_current_round_state
    current_round, timer, status, _ = get_current_round_state(redis_client)
    
    # Get stats for current round
    current_round_total_amount = 0
    current_round_total_bets = 0
    bets_by_number_list = []
    
    if current_round:
        current_round_bets = Bet.objects.filter(round=current_round)
        current_round_total_bets = current_round_bets.count()
        current_round_total_amount = current_round_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
        # Single query for bets by number (avoids 6 separate filter+aggregate+count)
        per_number = current_round_bets.values('number').annotate(
            amount=Sum('chip_amount'),
            count=Count('id')
        ).order_by('number')
        per_number_map = {r['number']: r for r in per_number}
        for number in range(1, 7):
            r = per_number_map.get(number, {})
            bets_by_number_list.append({
                'number': number,
                'amount': float(r.get('amount') or 0),
                'count': r.get('count') or 0
            })

    # Overall stats in one query
    overall = Bet.objects.aggregate(
        total_amount=Sum('chip_amount'),
        total_payout=Sum('payout_amount')
    )
    overall_total_amount = overall.get('total_amount') or 0
    overall_total_payout = overall.get('total_payout') or 0
    overall_total_profit = overall_total_amount - overall_total_payout
    total_bets_count = Bet.objects.count()

    # Prepare response data (JSON-serializable)
    data = {
        'timer': timer,
        'status': status,
        'current_round': {
            'round_id': current_round.round_id if current_round else None,
            'dice_result': current_round.dice_result if current_round else None,
            'dice_result_list': current_round.dice_result_list if current_round else [],
            'dice_1': current_round.dice_1 if current_round else None,
            'dice_2': current_round.dice_2 if current_round else None,
            'dice_3': current_round.dice_3 if current_round else None,
            'dice_4': current_round.dice_4 if current_round else None,
            'dice_5': current_round.dice_5 if current_round else None,
            'dice_6': current_round.dice_6 if current_round else None,
        } if current_round else None,
        'current_round_total_bets': current_round_total_bets,
        'current_round_total_amount': float(current_round_total_amount),
        'bets_by_number_list': bets_by_number_list,
        'total_bets': total_bets_count,
        'total_amount': float(overall_total_amount),
        'total_payout': float(overall_total_payout),
        'total_profit': float(overall_total_profit),
    }
    try:
        cache.set(ADMIN_DASHBOARD_DATA_CACHE_KEY, json.dumps(data), ADMIN_DASHBOARD_DATA_TTL)
    except Exception:
        pass
    return JsonResponse(data)

@admin_required
def set_individual_dice_view(request):
    """Admin view to set individual dice values (1-6 for each of 6 dice)
    All dice values must be provided and time restrictions are enforced
    """
    if request.method == 'POST':
        try:
            # Get current round state using helper
            from .utils import get_current_round_state, get_game_setting
            
            # Enforce local fallback for redis_client if global is missing/None
            local_redis = None
            try:
                 local_redis = redis_client
            except NameError:
                 pass
            
            round_obj, timer, status, _ = get_current_round_state(local_redis)

            # Get dice result time (needed for restriction check and finalization logic)
            dice_result_time = get_game_setting('DICE_RESULT_TIME', 51)

            # Check timer restriction
            if timer >= dice_result_time:
                    messages.error(request, f'Cannot set dice values after {dice_result_time} seconds. Use Manual Adjust mode to override.')
                    return redirect('dice_control')
            
            if not round_obj:
                messages.error(request, 'No active round')
                return redirect('dice_control')
            
            # Collect dice values (all dice required)
            dice_values_list = []  # For calculating result

            for i in range(1, 7):
                dice_value = request.POST.get(f'dice_{i}', '').strip()
                if dice_value:
                    try:
                        value = int(dice_value)
                        if 1 <= value <= 6:
                            dice_values_list.append(value)
                        else:
                            messages.error(request, f'Dice {i} value must be between 1-6')
                            return redirect('dice_control')
                    except ValueError:
                        messages.error(request, f'Invalid value for dice {i}')
                        return redirect('dice_control')
                else:
                    messages.error(request, f'Dice {i} value is required')
                    return redirect('dice_control')
            else:
                # Normal mode - must have all 6 values
                if len(dice_values_list) != 6:
                    messages.error(request, 'All 6 dice values are required')
                    return redirect('dice_control')
            
            # Apply updates to round object
            for i, value in enumerate(dice_values_list):
                setattr(round_obj, f'dice_{i+1}', value)
            
            # If we have at least some dice values, calculate result
            if dice_values_list:
                # Filter out None values for calculation
                valid_dice = [d for d in dice_values_list if d is not None]
                if valid_dice:
                    from .utils import determine_winning_number
                    most_common = determine_winning_number(valid_dice)
                    
                    round_obj.dice_result = most_common
                    
                    # Only finalize the round (status, payouts, broadcast) if we are at or past result time
                    should_finalize = timer >= dice_result_time
                    
                    if should_finalize:
                        round_obj.status = 'RESULT'
                        if not round_obj.result_time:
                            round_obj.result_time = timezone.now()
                    
                    round_obj.save()
                    
                    # Create or update dice result record
                    DiceResult.objects.update_or_create(
                        round=round_obj,
                        defaults={
                            'result': most_common,
                            'set_by': request.user
                        }
                    )
                    
                    # Update Redis with all current dice values
                    if redis_client:
                        try:
                            # 1. Update legacy current_round key
                            round_data = redis_client.get('current_round')
                            if round_data:
                                round_data = json.loads(round_data)
                                round_data['dice_result'] = most_common
                                # Update all dice values (use current from DB)
                                for i in range(1, 7):
                                    dice_val = getattr(round_obj, f'dice_{i}', None)
                                    if dice_val is not None:
                                        round_data[f'dice_{i}'] = dice_val
                                
                                if should_finalize:
                                    round_data['status'] = 'RESULT'
                                
                                redis_client.set('current_round', json.dumps(round_data))
                            
                            # 2. Update manual_dice_result for the engine to pick up
                            # Format: "1,2,3,4,5,6"
                            if all(d is not None for d in complete_dice):
                                manual_dice_str = ",".join([str(d) for d in complete_dice])
                                redis_client.set("manual_dice_result", manual_dice_str, ex=300)
                        except Exception:
                            pass
                    
                    # ONLY calculate payouts and broadcast if finalizing
                    if should_finalize:
                        # Calculate payouts based on dice values (frequency-based)
                        from .views import calculate_payouts
                        # Get complete dice values from round object
                        complete_dice = [
                            round_obj.dice_1, round_obj.dice_2, round_obj.dice_3,
                            round_obj.dice_4, round_obj.dice_5, round_obj.dice_6
                        ]
                        # Only calculate if we have all 6 dice values
                        if all(d is not None for d in complete_dice):
                            calculate_payouts(round_obj, dice_result=most_common, dice_values=complete_dice)
                        
                        # Broadcast to WebSocket
                        from channels.layers import get_channel_layer
                        from asgiref.sync import async_to_sync
                        channel_layer = get_channel_layer()
                        if channel_layer:
                            try:
                                async_to_sync(channel_layer.group_send)(
                                    'game_room',
                                    {
                                        'type': 'dice_result',
                                        'result': most_common,
                                        'dice_values': complete_dice if all(d is not None for d in complete_dice) else valid_dice,
                                        'round_id': round_obj.round_id,
                                    }
                                )
                            except Exception:
                                pass
                    
                    mode_text = " (Pre-set)" if not should_finalize else ""
                    
                    updated_text = ", ".join([f"D{i+1}:{v}" for i, v in enumerate(dice_values_list)])
                    messages.success(request, f'Dice values updated{mode_text}: {updated_text} | Result: {most_common}')
                else:
                    messages.error(request, 'At least one valid dice value is required')
            else:
                messages.error(request, 'No dice values provided')

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            from django.http import HttpResponse
            return HttpResponse(f"<html><body><h1>Error setting dice values</h1><pre>{error_trace}</pre><br><a href='/game-admin/dice-control/'>Back to Dice Control</a></body></html>")
    
    return redirect('dice_control')

@admin_required
def dice_control(request):
    """Dice control page with PIN protection"""
    try:

        if not has_menu_permission(request.user, 'dice_control'):
            messages.error(request, 'You do not have permission to access dice control.')
            return redirect('admin_dashboard')

        # PIN protection
        if request.method == 'POST' and 'pin' in request.POST:
            pin = request.POST.get('pin')
            if pin == getattr(settings, 'DICE_CONTROL_PIN', '1234'):
                request.session['dice_control_verified'] = True
                request.session.modified = True
                # Continue to GET logic
            else:
                return render(request, 'admin/dice_control_pin.html', {'error': 'Invalid PIN'})

        # Check if they are trying to perform an action (POST) without verification
        if request.method == 'POST' and not request.session.get('dice_control_verified'):
            # This handles cases where they might try to submit a dice control form directly
            return render(request, 'admin/dice_control_pin.html', {'error': 'Please verify your PIN first.'})

        if not request.session.get('dice_control_verified'):
            return render(request, 'admin/dice_control_pin.html')
            
        # Get current round state using helper
        from .utils import get_current_round_state, get_game_setting
        
        # Enforce local fallback for redis_client if global is missing/None
        local_redis = None
        try:
                local_redis = redis_client
        except NameError:
                pass
                
        current_round, timer, status, _ = get_current_round_state(local_redis)
        
        # Get stats for current round
        current_round_total_amount = 0
        current_round_total_bets = 0
        bets_by_number_list = []
        
        if current_round:
            current_round_bets = Bet.objects.filter(round=current_round)
            current_round_total_bets = current_round_bets.count()
            current_round_total_amount = current_round_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
            
            # Calculate bets by number
            for number in range(1, 7):
                number_bets = current_round_bets.filter(number=number)
                amount = number_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
                count = number_bets.count()
                bets_by_number_list.append({
                    'number': number,
                    'amount': amount,
                    'count': count
                })
        
        # Get dice mode
        from .views import get_dice_mode
        dice_mode = get_dice_mode()
        
        # Get timing settings for current round
        betting_close_time = current_round.betting_close_seconds if current_round else get_game_setting('BETTING_CLOSE_TIME', 30)
        dice_result_time = current_round.dice_result_seconds if current_round else get_game_setting('DICE_RESULT_TIME', 51)
        round_end_time = current_round.round_end_seconds if current_round else get_game_setting('ROUND_END_TIME', 80)

        context = get_admin_context(request, {
            'current_round': current_round,
            'timer': timer,
            'status': status,
            'dice_mode': dice_mode,
            'current_round_total_bets': current_round_total_bets,
            'current_round_total_amount': current_round_total_amount,
            'bets_by_number_list': bets_by_number_list,
            'betting_close_time': betting_close_time,
            'dice_result_time': dice_result_time,
            'round_end_time': round_end_time,
            'page': 'dice-control',
        })
        
        return render(request, 'admin/dice_control.html', context)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        from django.http import HttpResponse
        return HttpResponse(f"<html><body><h1>Error loading Dice Control Page</h1><pre>{error_trace}</pre><br><a href='/game-admin/dashboard/'>Back to Dashboard</a></body></html>")

@admin_required
def dice_controlled_rounds(request):
    """Redirect to Recent Rounds with controlled-only filter (controlled dice are shown there only)."""
    if not has_menu_permission(request.user, 'dice_control'):
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('admin_dashboard')
    from django.urls import reverse
    return redirect(reverse('recent_rounds') + '?controlled_only=1')

@admin_required
def recent_rounds(request):
    """Recent rounds page with search and filter"""
    if not has_menu_permission(request.user, 'recent_rounds'):
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('admin_dashboard')
    
    # Get search query and filters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    controlled_only = request.GET.get('controlled_only') == '1'
    
    # Get recent rounds with per-round bet count/sum from Bet table (use distinct names to avoid conflict with model fields)
    recent_rounds_list = GameRound.objects.annotate(
        round_bets_count=Count('bets'),
        round_bets_amount=Coalesce(Sum('bets__chip_amount'), Value(0)),
    )
    
    # Apply "controlled only" filter: only rounds where dice was set by an admin
    if controlled_only:
        controlled_round_ids = DiceResult.objects.filter(set_by__isnull=False).values_list('round_id', flat=True)
        recent_rounds_list = recent_rounds_list.filter(pk__in=controlled_round_ids)
    
    # Apply search filter
    if search_query:
        # Search by round_id or dice_result
        recent_rounds_list = recent_rounds_list.filter(
            Q(round_id__icontains=search_query) | 
            Q(dice_result__icontains=search_query)
        )
    
    # Apply status filter
    if status_filter:
        recent_rounds_list = recent_rounds_list.filter(status=status_filter)
    
    # Limit results and order by most recent
    recent_rounds_list = list(recent_rounds_list.order_by('-start_time')[:50])
    
    # Set of round IDs that were manually controlled (for "Controlled" badge in table)
    controlled_round_ids_set = set(DiceResult.objects.filter(set_by__isnull=False).values_list('round_id', flat=True))
    
    # Get recent bets (also with search if provided)
    recent_bets = Bet.objects.select_related('user', 'round').all()
    if search_query:
        recent_bets = recent_bets.filter(
            Q(round__round_id__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )
    recent_bets = recent_bets.order_by('-created_at')[:20]
    
    # Calculate stats
    total_rounds = GameRound.objects.count()
    total_bets_count = Bet.objects.count()
    total_bets_amount = Bet.objects.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
    
    # Dice control history: only rounds manually controlled by admin (set_by not null)
    dice_control_history = DiceResult.objects.filter(set_by__isnull=False).select_related('round', 'set_by').order_by('-set_at')[:50]
    
    context = get_admin_context(request, {
        'recent_rounds': recent_rounds_list,
        'controlled_round_ids': controlled_round_ids_set,
        'controlled_only': controlled_only,
        'recent_bets': recent_bets,
        'dice_control_history': dice_control_history,
        'total_rounds': total_rounds,
        'total_bets_count': total_bets_count,
        'total_bets_amount': total_bets_amount,
        'search_query': search_query,
        'status_filter': status_filter,
        'page': 'rounds',
    })
    
    return render(request, 'admin/recent_rounds.html', context)

@admin_required
def round_details(request, round_id):
    """Round details page showing all users who bet on this round"""
    try:
        round_obj = GameRound.objects.get(round_id=round_id)
    except GameRound.DoesNotExist:
        messages.error(request, 'Round not found.')
        return redirect('recent_rounds')
    
    # Get all bets for this round
    round_bets = Bet.objects.filter(round=round_obj).select_related('user').order_by('-created_at')
    
    # Calculate round stats
    total_bets_count = round_bets.count()
    total_bet_amount = round_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
    total_winners = round_bets.filter(is_winner=True).count()
    total_payouts = round_bets.aggregate(Sum('payout_amount'))['payout_amount__sum'] or 0
    
    # Get unique users who bet on this round
    unique_users = User.objects.filter(bets__round=round_obj).distinct()
    
    # Calculate bets by number
    bets_by_number_list = []
    for number in range(1, 7):
        number_bets = round_bets.filter(number=number)
        amount = number_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
        count = number_bets.count()
        bets_by_number_list.append({
            'number': number,
            'amount': amount,
            'count': count
        })
    
    context = get_admin_context(request, {
        'round': round_obj,
        'round_bets': round_bets,
        'unique_users': unique_users,
        'total_bets_count': total_bets_count,
        'total_bet_amount': total_bet_amount,
        'total_winners': total_winners,
        'total_payouts': total_payouts,
        'bets_by_number_list': bets_by_number_list,
        'page': 'round-details',
    })
    
    return render(request, 'admin/round_details.html', context)

@csrf_exempt
def user_details(request, user_id):
    """User details page showing all their bets and information"""
    logger = logging.getLogger(__name__)
    # Check admin permission manually to avoid redirect issues with @admin_required
    if not request.user.is_authenticated:
        from django.urls import reverse
        try:
            login_url = reverse('admin_login')
        except:
            login_url = '/game-admin/login/'
        return redirect(f"{login_url}?next={request.get_full_path()}")
    
    if not is_admin(request.user):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('/game-admin/login/')
    
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('recent_rounds')

    # Handle block/unblock and balance adjustment POST request
    if request.method == 'POST':
        action = request.POST.get('action')
        amount = request.POST.get('amount', '0').strip()
        utr_number = request.POST.get('utr_number', '').strip()

        # Block / Unblock user (any admin can block; cannot block self or superuser)
        if action in ('block', 'unblock'):
            if user_id == request.user.id:
                messages.error(request, 'You cannot block yourself.')
                return redirect(request.get_full_path())
            if user.is_superuser:
                messages.error(request, 'Cannot block a superuser.')
                return redirect(request.get_full_path())
            new_active = (action == 'unblock')
            if user.is_active != new_active:
                user.is_active = new_active
                user.save()
                # Invalidate Redis cache so next API call sees updated is_active
                try:
                    if redis_client:
                        cache_key = f"user_session:{user.id}"
                        redis_client.delete(cache_key)
                except Exception:
                    pass
            messages.success(request, f'User {user.username} has been {"unblocked" if new_active else "blocked"}.')
            return redirect(request.get_full_path())

        # Debug logging
        logger.info(f"Balance adjustment request: user={user_id}, action={action}, amount={amount}, utr={utr_number}, user={request.user.username}, authenticated={request.user.is_authenticated}, is_admin={is_admin(request.user)}")
        
        # Validate UTR number for deposit and withdraw actions
        if action in ['deposit', 'withdraw'] and not utr_number:
            messages.error(request, f'UTR number is mandatory for {action}.')
            return redirect(request.get_full_path())

        try:
            amount = Decimal(amount)
            if amount <= 0:
                messages.error(request, 'Amount must be greater than 0.')
                return redirect(request.get_full_path())

            wallet, _ = Wallet.objects.get_or_create(user=user)
            balance_before = wallet.balance

            if action == 'deposit':
                # Add money to user balance
                # Deposit money needs to be rotated 1 time
                amount_decimal = Decimal(str(amount))
                
                # 1️⃣ Update DB atomically
                Wallet.objects.filter(pk=wallet.pk).update(balance=F('balance') + amount_decimal)
                wallet.refresh_from_db()
                
                transaction_type = 'DEPOSIT'
                description = f"deposited by support_team (UTR: {utr_number})"
                
                # Also create a DepositRequest record so it shows in deposit list
                DepositRequest.objects.create(
                    user=user,
                    amount=amount_decimal,
                    status='APPROVED',
                    payment_method=None, # Manual adjustment
                    payment_reference=utr_number,
                    processed_by=request.user,
                    processed_at=timezone.now(),
                    admin_note=f'Manual deposit by support team. UTR: {utr_number}'
                )
                
                # 2️⃣ Update Redis atomically using INCRBYFLOAT
                try:
                    if redis_client:
                        redis_client.incrbyfloat(f"user_balance:{user.id}", float(amount_decimal))
                        logger.info(f"Updated Redis balance cache for user {user.id} after deposit: {wallet.balance}")
                except Exception as redis_err:
                    logger.error(f"Failed to update Redis balance for user {user.id}: {redis_err}")

                messages.success(request, f'Successfully deposited ₹{amount} to {user.username}\'s account.')
            elif action == 'withdraw':
                # Subtract money from user balance
                amount_decimal = Decimal(str(amount))
                
                # Check if balance is sufficient
                if wallet.balance < amount_decimal:
                    messages.error(request, f'Insufficient balance. Current balance: ₹{wallet.balance}')
                    return redirect(request.get_full_path())
                
                # 1️⃣ Update DB atomically
                Wallet.objects.filter(pk=wallet.pk).update(balance=F('balance') - amount_decimal)
                wallet.refresh_from_db()
                
                transaction_type = 'WITHDRAW'
                description = f"withdrawn by support_team (UTR: {utr_number})"
                
                # Also create a WithdrawRequest record so it shows in withdrawal list
                WithdrawRequest.objects.create(
                    user=user,
                    amount=amount_decimal,
                    status='COMPLETED',
                    withdrawal_method='ADMIN_ADJUSTMENT',
                    withdrawal_details=f'Withdrawn by Support Team. UTR: {utr_number}',
                    processed_by=request.user,
                    processed_at=timezone.now(),
                    admin_note=f'Manual withdrawal by support team. UTR: {utr_number}',
                    utr_number=utr_number
                )
                
                # 2️⃣ Update Redis atomically using INCRBYFLOAT (negative)
                try:
                    if redis_client:
                        redis_client.incrbyfloat(f"user_balance:{user.id}", -float(amount_decimal))
                        logger.info(f"Updated Redis balance cache for user {user.id}: {wallet.balance}")
                except Exception as redis_err:
                    logger.error(f"Failed to update Redis balance for user {user.id}: {redis_err}")

                messages.success(request, f'Successfully withdrew ₹{amount} from {user.username}\'s account.')
            elif action == 'adjust_remove':
                # Subtract money from user balance (Adjustment)
                amount_decimal = Decimal(str(amount))
                
                # Check if balance is sufficient
                if wallet.balance < amount_decimal:
                    messages.error(request, f'Insufficient balance for adjustment. Current balance: ₹{wallet.balance}')
                    return redirect(request.get_full_path())
                
                # 1️⃣ Update DB atomically (F is imported at module level)
                Wallet.objects.filter(pk=wallet.pk).update(balance=F('balance') - amount_decimal)
                wallet.refresh_from_db()
                
                transaction_type = 'WITHDRAW'
                description = f"balance adjustment (removed) by admin"
                
                # 2️⃣ Update Redis atomically using INCRBYFLOAT (negative)
                try:
                    if redis_client:
                        redis_client.incrbyfloat(f"user_balance:{user.id}", -float(amount_decimal))
                        logger.info(f"Updated Redis balance cache for user {user.id} after adjustment: {wallet.balance}")
                except Exception as redis_err:
                    logger.error(f"Failed to update Redis balance for user {user.id}: {redis_err}")

                messages.success(request, f'Successfully adjusted balance: Removed ₹{amount} from {user.username}\'s account.')
            else:
                messages.error(request, 'Invalid action.')
                return redirect(request.get_full_path())

            # Create transaction record
            Transaction.objects.create(
                user=user,
                transaction_type=transaction_type,
                amount=amount_decimal,
                balance_before=balance_before,
                balance_after=wallet.balance,
                description=description
            )

            return redirect(request.get_full_path())

        except ValueError:
            messages.error(request, 'Invalid amount format.')
            return redirect(request.get_full_path())
        except Exception as e:
            logger.error(f"Error adjusting balance for user {user_id}: {e}")
            messages.error(request, f'Error processing request: {str(e)}')
            return redirect(request.get_full_path())

    # Get user's wallet
    wallet, _ = Wallet.objects.get_or_create(user=user)
    
    # Get active tab from query params
    active_tab = request.GET.get('tab', 'all')
    
    # Get all bets by this user
    user_bets = Bet.objects.filter(user=user).select_related('round').order_by('-created_at')
    if active_tab == 'bets':
        user_bets = user_bets[:200]
    else:
        user_bets = user_bets[:50]
    
    # Calculate user stats (always needed)
    total_bets = Bet.objects.filter(user=user).count()
    total_bet_amount = Bet.objects.filter(user=user).aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
    total_wins = Bet.objects.filter(user=user, is_winner=True).count()
    total_payouts = Bet.objects.filter(user=user).aggregate(Sum('payout_amount'))['payout_amount__sum'] or 0
    
    # Get user's transactions
    user_transactions = Transaction.objects.filter(user=user).order_by('-created_at')
    if active_tab == 'transactions':
        user_transactions = user_transactions[:200]
    else:
        user_transactions = user_transactions[:50]
    
    # Get user's deposit requests
    user_deposits = DepositRequest.objects.filter(user=user).order_by('-created_at')
    if active_tab == 'deposits':
        user_deposits = user_deposits[:100]
    else:
        user_deposits = user_deposits[:20]

    # Get user's withdraw requests
    user_withdrawals = WithdrawRequest.objects.filter(user=user).order_by('-created_at')
    if active_tab == 'withdrawals':
        user_withdrawals = user_withdrawals[:100]
    else:
        user_withdrawals = user_withdrawals[:20]
    
    # Admin specific stats
    admin_stats = None
    assigned_users = None
    if user.is_staff:
        # Date filtering for reports
        from datetime import timedelta
        today = timezone.now().date()
        
        # Get filter type: today, week, month, custom
        report_range = request.GET.get('report_range', 'today')
        start_date = today
        end_date = today
        
        if report_range == 'week':
            start_date = today - timedelta(days=today.weekday())
        elif report_range == 'month':
            start_date = today.replace(day=1)
        elif report_range == 'custom':
            try:
                start_date_str = request.GET.get('start_date')
                end_date_str = request.GET.get('end_date')
                if start_date_str:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                if end_date_str:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        
        assigned_users_qs = User.objects.filter(worker=user, is_staff=False).order_by('-date_joined')
        assigned_users_count = assigned_users_qs.count()
        
        # Filtered reports
        deposits_qs = DepositRequest.objects.filter(processed_by=user, status='APPROVED', processed_at__date__gte=start_date, processed_at__date__lte=end_date)
        withdrawals_qs = WithdrawRequest.objects.filter(processed_by=user, status='COMPLETED', processed_at__date__gte=start_date, processed_at__date__lte=end_date)
        
        admin_stats = {
            'assigned_users_count': assigned_users_count,
            'report_range': report_range,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'deposits_count': deposits_qs.count(),
            'deposits_amount': deposits_qs.aggregate(Sum('amount'))['amount__sum'] or 0,
            'withdrawals_count': withdrawals_qs.count(),
            'withdrawals_amount': withdrawals_qs.aggregate(Sum('amount'))['amount__sum'] or 0,
        }
        
        # Get assigned users list (paginated)
        assigned_users = assigned_users_qs[:100] # Limit to 100 for now
    
    # Show Block/Unblock to any admin when viewing another user who is not a superuser
    can_block_user = (request.user.id != user_id and not user.is_superuser)
    context = get_admin_context(request, {
        'player': user,
        'wallet': wallet,
        # Wallet formula:
        # unavailable = max(0, balance - turnover)
        # withdrawable = min(balance, turnover)
        'wallet_unavailable': max(Decimal('0.00'), Decimal(str(wallet.balance)) - Decimal(str(wallet.turnover))),
        'wallet_withdrawable': max(Decimal('0.00'), min(Decimal(str(wallet.balance)), Decimal(str(wallet.turnover)))),
        'user_bets': user_bets,
        'total_bets': total_bets,
        'total_bet_amount': total_bet_amount,
        'total_wins': total_wins,
        'total_payouts': total_payouts,
        'user_transactions': user_transactions,
        'user_deposits': user_deposits,
        'user_withdrawals': user_withdrawals,
        'active_tab': active_tab,
        'admin_stats': admin_stats,
        'assigned_users': assigned_users,
        'can_block_user': can_block_user,
        'page': 'user-details',
    })
    
    return render(request, 'admin/user_details.html', context)

@admin_required
def testing_dashboard(request):
    """Testing dashboard for simulations and load testing"""
    if not is_super_admin(request.user):
        messages.error(request, 'Only super admins can access the testing dashboard.')
        return redirect('admin_dashboard')
    
    admin_profile = get_admin_profile(request.user)
    context = get_admin_context(request, {
        'page': 'testing-dashboard',
        'admin_profile': admin_profile,
    })
    return render(request, 'admin/testing_dashboard.html', context)

@admin_required
def start_simulation(request):
    """API endpoint to start user/bet simulation"""
    if not is_super_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_count = int(data.get('user_count', 10))
            bets_per_user = int(data.get('bets_per_user', 5))
            chip_amount = float(data.get('chip_amount', 10))
            
            # Use current request's host to determine base URL
            protocol = 'https' if request.is_secure() else 'http'
            host = request.get_host()
            load_tester.base_url = f"{protocol}://{host}"
            
            load_tester.run_simulation(user_count, bets_per_user, chip_amount)
            return JsonResponse({'status': 'started', 'results': load_tester.get_status()})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'POST required'}, status=405)

@admin_required
def stop_simulation(request):
    """API endpoint to stop the ongoing simulation"""
    if not is_super_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    load_tester.results['is_running'] = False
    return JsonResponse({'status': 'stopped'})

@admin_required
def simulation_status(request):
    """API endpoint to get simulation status"""
    if not is_super_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    return JsonResponse(load_tester.get_status())

@admin_required
def all_bets(request):
    """All bets page"""
    if not has_menu_permission(request.user, 'all_bets'):
        messages.error(request, 'You do not have permission to view all bets.')
        return redirect('admin_dashboard')

    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all') # all, winners, losers

    # Get all bets
    all_bets_list = Bet.objects.select_related('user', 'round').all().order_by('-created_at')

    # If not super admin, filter by worker's clients
    if not is_super_admin(request.user):
        all_bets_list = all_bets_list.filter(user__worker=request.user)

    # Apply search filter
    if search_query:
        all_bets_list = all_bets_list.filter(
            Q(user__username__icontains=search_query) |
            Q(user__phone_number__icontains=search_query) |
            Q(round__round_id__icontains=search_query)
        )

    # Apply status filter
    if status_filter == 'winners':
        all_bets_list = all_bets_list.filter(is_winner=True)
    elif status_filter == 'losers':
        all_bets_list = all_bets_list.filter(is_winner=False)

    # Single aggregate for all stats (avoids 4 separate queries)
    stats = all_bets_list.aggregate(
        total_bets_count=Count('id'),
        total_bets_amount=Sum('chip_amount'),
        total_payouts=Sum('payout_amount'),
        total_winners=Count('id', filter=Q(is_winner=True))
    )
    total_bets_count = stats.get('total_bets_count') or 0
    total_bets_amount = stats.get('total_bets_amount') or 0
    total_payouts = stats.get('total_payouts') or 0
    total_winners = stats.get('total_winners') or 0

    # Limit results for performance
    all_bets_list = list(all_bets_list[:200])

    context = get_admin_context(request, {
        'all_bets': all_bets_list,
        'total_bets_count': total_bets_count,
        'total_bets_amount': total_bets_amount,
        'total_payouts': total_payouts,
        'total_winners': total_winners,
        'search_query': search_query,
        'status_filter': status_filter,
        'page': 'all-bets',
    })

    return render(request, 'admin/all_bets.html', context)

@admin_required
def wallets(request):
    """Wallets page with filters and pagination"""
    if not has_menu_permission(request.user, 'wallets'):
        messages.error(request, 'You do not have permission to view wallets.')
        return redirect('admin_dashboard')
        
    # Get filter parameters
    balance_filter = request.GET.get('balance', 'all')  # all, has_balance, zero
    search_query = request.GET.get('search', '').strip()
    sort_by = request.GET.get('sort', 'balance_desc')  # balance_desc, balance_asc, username_asc, username_desc
    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1
    
    # Build query
    wallets_query = Wallet.objects.select_related('user').all()
    
    # Apply balance filter
    if balance_filter == 'has_balance':
        wallets_query = wallets_query.filter(balance__gt=0)
    elif balance_filter == 'zero':
        wallets_query = wallets_query.filter(balance=0)
    # 'all' shows all wallets
    
    # Apply search
    if search_query:
        wallets_query = wallets_query.filter(
            Q(user__username__icontains=search_query) |
            Q(user__phone_number__icontains=search_query)
        )
    
    # Apply sorting
    if sort_by == 'balance_desc':
        wallets_query = wallets_query.order_by('-balance')
    elif sort_by == 'balance_asc':
        wallets_query = wallets_query.order_by('balance')
    elif sort_by == 'username_asc':
        wallets_query = wallets_query.order_by('user__username')
    elif sort_by == 'username_desc':
        wallets_query = wallets_query.order_by('-user__username')
    else:
        wallets_query = wallets_query.order_by('-balance')  # default
    
    # Calculate stats (before pagination for accurate totals)
    total_wallets = Wallet.objects.count()
    total_balance = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0
    active_wallets = Wallet.objects.filter(balance__gt=0).count()
    zero_balance_wallets = Wallet.objects.filter(balance=0).count()
    
    # Pagination - 50 wallets per page for better performance
    paginator = Paginator(wallets_query, 50)
    try:
        page_obj = paginator.get_page(page_number)
    except Exception:
        page_obj = None
    
    context = get_admin_context(request, {
        'wallets': page_obj if page_obj else wallets_query[:50],  # Fallback to first 50 if pagination fails
        'page_obj': page_obj,
        'total_wallets': total_wallets,
        'total_balance': total_balance,
        'active_wallets': active_wallets,
        'zero_balance_wallets': zero_balance_wallets,
        'balance_filter': balance_filter,
        'search_query': search_query,
        'sort_by': sort_by,
        'page': 'wallets',
    })
    
    return render(request, 'admin/wallets.html', context)

@admin_required
def deposit_requests(request):
    """Deposit requests page"""
    if not has_menu_permission(request.user, 'deposit_requests'):
        messages.error(request, 'You do not have permission to view deposit requests.')
        return redirect('admin_dashboard')
        
    # Get search and status filters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    
    # Base queryset for deposit requests
    deposit_requests_qs = DepositRequest.objects.select_related('user', 'processed_by').all()
    
    # Filter by assigned worker (if not super admin)
    if not is_super_admin(request.user):
        deposit_requests_qs = deposit_requests_qs.filter(user__worker=request.user)
    
    # Apply filters
    if search_query:
        deposit_requests_qs = deposit_requests_qs.filter(
            Q(user__username__icontains=search_query) |
            Q(payment_reference__icontains=search_query) |
            Q(amount__icontains=search_query)
        )
        
    if status_filter:
        deposit_requests_qs = deposit_requests_qs.filter(status=status_filter)
        
    # Order by most recent
    deposit_requests_qs = deposit_requests_qs.order_by('-created_at')
    
    # Paginate: 50 per page for performance
    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1
    paginator = Paginator(deposit_requests_qs, 50)
    try:
        page_obj = paginator.get_page(page_number)
    except Exception:
        page_obj = paginator.get_page(1)
    deposit_requests_list = page_obj.object_list
    
    # Stats (single filtered base for counts; avoid scanning full table multiple times)
    stats_base = DepositRequest.objects.all()
    if not is_super_admin(request.user):
        stats_base = stats_base.filter(user__worker=request.user)
    total_requests = stats_base.count()
    pending_requests = stats_base.filter(status='PENDING').count()
    approved_requests = stats_base.filter(status='APPROVED').count()
    rejected_requests = stats_base.filter(status='REJECTED').count()
    total_amount = stats_base.filter(status='APPROVED').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_amount = stats_base.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Latest request ID for polling
    latest_request_id = stats_base.order_by('-id').first()
    latest_id = latest_request_id.id if latest_request_id else 0
    
    context = get_admin_context(request, {
        'deposit_requests': deposit_requests_list,
        'page_obj': page_obj,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'rejected_requests': rejected_requests,
        'total_amount': total_amount,
        'pending_amount': pending_amount,
        'latest_request_id': latest_id,
        'search_query': search_query,
        'status_filter': status_filter,
        'page': 'deposit-requests',
    })
    
    return render(request, 'admin/deposit_requests.html', context)


@admin_required
def check_new_deposit_requests(request):
    """API endpoint to check for new deposit requests"""
    last_id = int(request.GET.get('last_id', 0))
    
    # Get new pending requests
    new_requests = DepositRequest.objects.filter(
        id__gt=last_id,
        status='PENDING'
    )
    
    # Filter by assigned worker (if not super admin)
    if not is_super_admin(request.user):
        new_requests = new_requests.filter(user__worker=request.user)
        
    new_requests = new_requests.select_related('user').order_by('-id')[:10]
    
    requests_data = []
    for req in new_requests:
        requests_data.append({
            'id': req.id,
            'user': req.user.username,
            'amount': float(req.amount),
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    
    return JsonResponse({
        'new_requests': requests_data,
        'latest_id': DepositRequest.objects.order_by('-id').first().id if DepositRequest.objects.exists() else last_id,
        'pending_count': DepositRequest.objects.filter(status='PENDING').count(),
    })

@admin_required
def approve_deposit(request, pk):
    """Approve a deposit request"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method. Please use the approve button.')
        return redirect('deposit_requests')
    
    try:
        with db_transaction.atomic():
            # select_for_update must be inside the transaction
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != 'PENDING':
                messages.error(request, 'Deposit request has already been processed.')
                return redirect('deposit_requests')
            
            wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            balance_before = wallet.balance
            
            # Calculate final amount with USDT bonus if applicable
            final_amount = deposit.amount
            bonus_amount = Decimal('0.00')
            if deposit.payment_method and deposit.payment_method.method_type in ['USDT_TRC20', 'USDT_BEP20']:
                bonus_amount = deposit.amount * Decimal('0.05')
                final_amount += bonus_amount
            
            # 1️⃣ Update DB atomically
            Wallet.objects.filter(pk=wallet.pk).update(balance=F('balance') + final_amount)
            wallet.refresh_from_db()
            
            deposit.status = 'APPROVED'
            deposit.processed_by = request.user
            deposit.processed_at = timezone.now()
            
            # Compulsory UTR verification
            utr = request.POST.get('utr', '').strip()
            if not utr:
                messages.error(request, 'UTR number is compulsory for approving deposits.')
                return redirect('deposit_requests')
            
            deposit.payment_reference = utr
            
            # If there's a note from the approval process, save it
            note = request.POST.get('note', '')
            if note:
                deposit.admin_note = note
            deposit.save()

            # 2️⃣ Update Redis atomically using INCRBYFLOAT
            try:
                from game.views import redis_client
                if redis_client:
                    redis_client.incrbyfloat(f"user_balance:{deposit.user.id}", float(final_amount))
                    logger.info(f"Updated Redis balance for user {deposit.user.id} after deposit approval: {wallet.balance}")
            except Exception as re_err:
                logger.error(f"Failed to update Redis balance for user {deposit.user.id} after deposit approval: {re_err}")
            
            Transaction.objects.create(
                user=deposit.user,
                transaction_type='DEPOSIT',
                amount=final_amount,
                balance_before=balance_before,
                balance_after=wallet.balance,
                description=f"Manual deposit approved #{deposit.id}{f' (Includes 5% USDT bonus: ₹{bonus_amount})' if bonus_amount > 0 else ''}{f'. {deposit.admin_note}' if deposit.admin_note else ''}",
            )

            # Handle referral bonus
            referrer = deposit.user.referred_by
            if referrer:
                from accounts.referral_logic import calculate_referral_bonus, check_and_award_milestone_bonus
                referral_bonus = calculate_referral_bonus(deposit.amount)
                if referral_bonus > 0:
                    ref_wallet, _ = Wallet.objects.get_or_create(user=referrer)
                    ref_wallet = Wallet.objects.select_for_update().get(pk=ref_wallet.pk)
                    ref_balance_before = ref_wallet.balance
                    # Referral bonus needs to be rotated 1 time
                    ref_wallet.add(referral_bonus, is_bonus=True)
                    # ref_wallet.save() # ref_wallet.add already calls save()

                    Transaction.objects.create(
                        user=referrer,
                        transaction_type='REFERRAL_BONUS',
                        amount=referral_bonus,
                        balance_before=ref_balance_before,
                        balance_after=ref_wallet.balance,
                        description=f"Referral bonus from {deposit.user.username}'s deposit of ₹{deposit.amount}",
                    )
                    # 2️⃣ Update Redis for referrer atomically
                    try:
                        if redis_client:
                            redis_client.incrbyfloat(f"user_balance:{referrer.id}", float(referral_bonus))
                    except: pass
                    # Check for milestone bonus
                    check_and_award_milestone_bonus(referrer)
        
        messages.success(request, f"Deposit request #{deposit.id} approved. ₹{final_amount} added to {deposit.user.username}'s wallet.{f' (Includes ₹{bonus_amount} USDT bonus)' if bonus_amount > 0 else ''}")
    except DepositRequest.DoesNotExist:
        messages.error(request, 'Deposit request not found.')
    except Exception as e:
        messages.error(request, f'Error approving deposit: {str(e)}')
        import traceback
        traceback.print_exc()
    
    return redirect('deposit_requests')

@admin_required
def reject_deposit(request, pk):
    """Reject a deposit request"""
    if request.method == 'POST':
        note = request.POST.get('note', '')
        try:
            with db_transaction.atomic():
                # select_for_update must be inside the transaction
                deposit = DepositRequest.objects.select_for_update().get(pk=pk)
                if deposit.status != 'PENDING':
                    messages.error(request, 'Deposit request has already been processed.')
                    return redirect('deposit_requests')

                deposit.status = 'REJECTED'
                deposit.admin_note = note
                deposit.processed_by = request.user
                deposit.processed_at = timezone.now()
                deposit.save()

            messages.success(request, f'Deposit request #{deposit.id} rejected.')
        except DepositRequest.DoesNotExist:
            messages.error(request, 'Deposit request not found.')
        except Exception as e:
            messages.error(request, f'Error rejecting deposit: {str(e)}')
            import traceback
            traceback.print_exc()

    return redirect('deposit_requests')

@admin_required
def edit_deposit_amount(request, pk):
    """Edit deposit request amount"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method. Please use the edit button.')
        return redirect('deposit_requests')

    try:
        with db_transaction.atomic():
            # select_for_update must be inside the transaction
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != 'PENDING':
                messages.error(request, 'Deposit request has already been processed.')
                return redirect('deposit_requests')

            old_amount = deposit.amount
            new_amount = decimal.Decimal(request.POST.get('new_amount', '0').strip())
            edit_reason = request.POST.get('edit_reason', '').strip()

            if new_amount <= 0:
                messages.error(request, 'Amount must be greater than 0.')
                return redirect('deposit_requests')

            # Update the amount
            deposit.amount = new_amount

            # Add edit information to admin_note
            edit_info = f"[AMOUNT EDITED: ₹{old_amount} → ₹{new_amount}"
            if edit_reason:
                edit_info += f" | Reason: {edit_reason}"
            edit_info += "]"

            if deposit.admin_note:
                deposit.admin_note += " | " + edit_info
            else:
                deposit.admin_note = edit_info

            deposit.save()

        messages.success(request, f"Deposit request #{deposit.id} amount updated from ₹{old_amount} to ₹{new_amount}.")
    except DepositRequest.DoesNotExist:
        messages.error(request, 'Deposit request not found.')
    except decimal.InvalidOperation:
        messages.error(request, 'Invalid amount format.')
    except Exception as e:
        messages.error(request, f'Error updating deposit amount: {str(e)}')
        import traceback
        traceback.print_exc()

    return redirect('deposit_requests')


@admin_required
def withdraw_requests(request):
    """Withdraw requests page"""
    if not has_menu_permission(request.user, 'withdraw_requests'):
        messages.error(request, 'You do not have permission to view withdraw requests.')
        return redirect('admin_dashboard')

    # Get search and status filters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()

    # Get all withdraw requests
    withdraw_requests_list = WithdrawRequest.objects.select_related('user', 'processed_by').all()
    
    # Filter by assigned worker (if not super admin)
    if not is_super_admin(request.user):
        withdraw_requests_list = withdraw_requests_list.filter(user__worker=request.user)
    
    # Apply filters
    if search_query:
        withdraw_requests_list = withdraw_requests_list.filter(
            Q(user__username__icontains=search_query) |
            Q(user__phone_number__icontains=search_query) |
            Q(withdrawal_details__icontains=search_query) |
            Q(amount__icontains=search_query)
        )
        
    if status_filter:
        if status_filter == 'SUCCESS':
            withdraw_requests_list = withdraw_requests_list.filter(status__in=['APPROVED', 'COMPLETED'])
        else:
            withdraw_requests_list = withdraw_requests_list.filter(status=status_filter)
        
    # Order by most recent
    withdraw_requests_list = withdraw_requests_list.order_by('-created_at')

    # Calculate stats (totals based on full dataset)
    stats_base = WithdrawRequest.objects.all()
    total_requests = stats_base.count()
    pending_requests = stats_base.filter(status='PENDING').count()
    approved_requests = stats_base.filter(status='APPROVED').count()
    rejected_requests = stats_base.filter(status='REJECTED').count()
    total_amount = stats_base.filter(status='APPROVED').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_amount = stats_base.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Get the latest request ID for polling
    latest_request_id = stats_base.order_by('-id').first()
    latest_id = latest_request_id.id if latest_request_id else 0
    
    context = get_admin_context(request, {
        'withdraw_requests': withdraw_requests_list,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'rejected_requests': rejected_requests,
        'total_amount': total_amount,
        'pending_amount': pending_amount,
        'latest_request_id': latest_id,
        'search_query': search_query,
        'status_filter': status_filter,
        'page': 'withdraw-requests',
    })

    return render(request, 'admin/withdraw_requests.html', context)


@admin_required
def check_new_withdraw_requests(request):
    """API endpoint to check for new withdraw requests"""
    last_id = int(request.GET.get('last_id', 0))
    
    # Get new pending requests
    new_requests = WithdrawRequest.objects.filter(
        id__gt=last_id,
        status='PENDING'
    )
    
    # Filter by assigned worker (if not super admin)
    if not is_super_admin(request.user):
        new_requests = new_requests.filter(user__worker=request.user)
        
    new_requests = new_requests.select_related('user').order_by('-id')[:10]
    
    requests_data = []
    for req in new_requests:
        requests_data.append({
            'id': req.id,
            'user': req.user.username,
            'amount': float(req.amount),
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    
    return JsonResponse({
        'new_requests': requests_data,
        'latest_id': WithdrawRequest.objects.order_by('-id').first().id if WithdrawRequest.objects.exists() else last_id,
        'pending_count': WithdrawRequest.objects.filter(status='PENDING').count(),
    })

@admin_required
def approve_withdraw(request, pk):
    """Approve a withdraw request - Deducts money from wallet and sets status to COMPLETED immediately"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method. Please use the approve button.')
        return redirect('withdraw_requests')
    
    try:
        with db_transaction.atomic():
            # select_for_update must be inside the transaction
            withdraw = WithdrawRequest.objects.select_for_update().get(pk=pk)
            if withdraw.status != 'PENDING':
                messages.error(request, 'Withdraw request has already been processed.')
                return redirect('withdraw_requests')
            
            wallet, _ = Wallet.objects.get_or_create(user=withdraw.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            
            if wallet.balance < withdraw.amount:
                messages.error(request, f'Insufficient balance in {withdraw.user.username}\'s wallet.')
                return redirect('withdraw_requests')

            # 1️⃣ Money is already deducted from Redis and DB during initiation
            # We just update the status to COMPLETED
            withdraw.status = 'COMPLETED'
            withdraw.processed_by = request.user
            withdraw.processed_at = timezone.now()
            
            # If there's a note or UTR from the approval process, save it
            note = request.POST.get('note', '')
            utr_number = request.POST.get('utr_number', '').strip()
            
            if note:
                withdraw.admin_note = note
            if utr_number:
                withdraw.utr_number = utr_number
                
            withdraw.save()

            logger.info(f"Withdrawal request #{withdraw.id} approved by admin {request.user.username}")
            
            # Automatically save/update bank details upon approval
            try:
                from accounts.models import UserBankDetail
                import re
                
                details_text = withdraw.withdrawal_details
                method = withdraw.withdrawal_method
                
                # Logic to extract fields from the formatted details string
                acc_name = ""
                bank_name = ""
                acc_num = ""
                ifsc = ""
                upi_id = ""
                
                if "UPI ID:" in details_text:
                    upi_match = re.search(r"UPI ID:\s*([^\n]+)", details_text)
                    name_match = re.search(r"Name:\s*([^\n]+)", details_text)
                    if upi_match: upi_id = upi_match.group(1).strip()
                    if name_match: acc_name = name_match.group(1).strip()
                else:
                    name_match = re.search(r"Name:\s*([^\n]+)", details_text)
                    bank_match = re.search(r"Bank:\s*([^\n]+)", details_text)
                    num_match = re.search(r"A/C:\s*([^\n]+)", details_text)
                    ifsc_match = re.search(r"IFSC:\s*([^\n]+)", details_text)
                    
                    if name_match: acc_name = name_match.group(1).strip()
                    if bank_match: bank_name = bank_match.group(1).strip()
                    if num_match: acc_num = num_match.group(1).strip()
                    if ifsc_match: ifsc = ifsc_match.group(1).strip()

                if acc_name and (upi_id or acc_num):
                    detail_obj = None
                    if upi_id:
                        detail_obj = UserBankDetail.objects.filter(user=withdraw.user, upi_id=upi_id).first()
                    elif acc_num:
                        detail_obj = UserBankDetail.objects.filter(user=withdraw.user, account_number=acc_num).first()
                    
                    if detail_obj:
                        detail_obj.save()
                    else:
                        UserBankDetail.objects.create(
                            user=withdraw.user,
                            account_name=acc_name,
                            bank_name=bank_name,
                            account_number=acc_num,
                            ifsc_code=ifsc,
                            upi_id=upi_id
                        )
            except Exception:
                pass
        
        messages.success(request, f'Withdraw request #{withdraw.id} approved and payment completed. ₹{withdraw.amount} deducted from {withdraw.user.username}\'s wallet.')
    except WithdrawRequest.DoesNotExist:
        messages.error(request, 'Withdraw request not found.')
    except Exception as e:
        messages.error(request, f'Error processing withdraw: {str(e)}')
    
    return redirect('withdraw_requests')

@admin_required
def complete_withdraw_payment(request, pk):
    """Finalize a withdraw request with UTR number after payment is completed"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('withdraw_requests')
    
    utr_number = request.POST.get('utr_number', '').strip()
    if not utr_number:
        messages.error(request, 'UTR number is required to complete payment.')
        return redirect('withdraw_requests')

    try:
        withdraw = WithdrawRequest.objects.get(pk=pk)
        if withdraw.status != 'APPROVED':
            messages.error(request, 'Only approved requests can be marked as payment completed.')
            return redirect('withdraw_requests')
        
        withdraw.status = 'COMPLETED'
        withdraw.utr_number = utr_number
        withdraw.save()
        
        messages.success(request, f'Payment completed for withdraw request #{withdraw.id}. UTR: {utr_number}')
    except WithdrawRequest.DoesNotExist:
        messages.error(request, 'Withdraw request not found.')
    except Exception as e:
        messages.error(request, f'Error completing payment: {str(e)}')
    
    return redirect('withdraw_requests')

@admin_required
def reject_withdraw(request, pk):
    """Reject a withdraw request"""
    if request.method == 'POST':
        note = request.POST.get('note', '')
        try:
            with db_transaction.atomic():
                # select_for_update must be inside the transaction
                withdraw = WithdrawRequest.objects.select_for_update().get(pk=pk)
                if withdraw.status != 'PENDING':
                    messages.error(request, 'Withdraw request has already been processed.')
                    return redirect('withdraw_requests')
                
                # 1️⃣ Refund money to Redis immediately
                try:
                    from game.views import redis_client
                    if redis_client:
                        redis_client.incrbyfloat(f"user_balance:{withdraw.user.id}", float(withdraw.amount))
                        logger.info(f"Refunded Redis balance for user {withdraw.user.id} after withdrawal rejection: {withdraw.amount}")
                except Exception as re_err:
                    logger.error(f"Failed to refund Redis balance for user {withdraw.user.id}: {re_err}")

                # 2️⃣ Queue refund event to worker
                refund_event = {
                    'type': 'reject_withdraw_refund',
                    'user_id': str(withdraw.user.id),
                    'withdraw_id': str(withdraw.id),
                    'amount': str(withdraw.amount),
                    'note': note,
                    'round_id': 'WITHDRAW',
                    'timestamp': timezone.now().isoformat()
                }
                if redis_client:
                    redis_client.xadd('bet_stream', refund_event, maxlen=10000)

                withdraw.status = 'REJECTED'
                withdraw.admin_note = note
                withdraw.processed_by = request.user
                withdraw.processed_at = timezone.now()
                withdraw.save()
            
            messages.success(request, f'Withdraw request #{withdraw.id} rejected and funds refunded to user.')
        except WithdrawRequest.DoesNotExist:
            messages.error(request, 'Withdraw request not found.')
        except Exception as e:
            messages.error(request, f'Error rejecting withdraw: {str(e)}')
    
    return redirect('withdraw_requests')

@admin_required
def transactions(request):
    """Reports page showing financial summary statistics"""
    if not has_menu_permission(request.user, 'transactions'):
        messages.error(request, 'You do not have permission to view reports.')
        return redirect('admin_dashboard')

    # Get search filter
    search_query = request.GET.get('search', '').strip()
    
    # Base transaction queryset
    transactions_query = Transaction.objects.all()
    
    # Apply search filter (filter by user)
    if search_query:
        transactions_query = transactions_query.filter(
            Q(user__username__icontains=search_query) |
            Q(user__phone_number__icontains=search_query)
        )

    # Calculate stats directly from database
    total_transactions = transactions_query.count()
    total_deposits = transactions_query.filter(transaction_type='DEPOSIT').aggregate(Sum('amount'))['amount__sum'] or 0
    total_withdraws = transactions_query.filter(transaction_type='WITHDRAW').aggregate(Sum('amount'))['amount__sum'] or 0
    total_bets = transactions_query.filter(transaction_type='BET').aggregate(Sum('amount'))['amount__sum'] or 0
    total_wins = transactions_query.filter(transaction_type='WIN').aggregate(Sum('amount'))['amount__sum'] or 0
    admin_profit = total_bets - total_wins

    # Calculate last 10 days profit data for chart
    from datetime import timedelta
    from django.db.models.functions import TruncDate
    
    # Changed from 30 days to 10 days as requested
    days_count = 10
    start_date = timezone.now().date() - timedelta(days=days_count-1)
    daily_stats = transactions_query.filter(
        created_at__date__gte=start_date,
        transaction_type__in=['BET', 'WIN']
    ).annotate(
        date=TruncDate('created_at')
    ).values('date', 'transaction_type').annotate(
        daily_amount=Sum('amount')
    ).order_by('date')

    # Process daily stats into a format for the chart
    profit_data_map = {}
    for i in range(days_count):
        date = start_date + timedelta(days=i)
        profit_data_map[date] = 0

    for stat in daily_stats:
        date = stat['date']
        amount = stat['daily_amount']
        if stat['transaction_type'] == 'BET':
            profit_data_map[date] += amount
        else:
            profit_data_map[date] -= amount

    # Convert to sorted lists for the chart
    chart_labels = [date.strftime('%b %d') for date in sorted(profit_data_map.keys())]
    chart_data = [float(profit_data_map[date]) for date in sorted(profit_data_map.keys())]

    context = get_admin_context(request, {
        'total_transactions': total_transactions,
        'total_deposits': total_deposits,
        'total_withdraws': total_withdraws,
        'total_bets': total_bets,
        'total_wins': total_wins,
        'admin_profit': admin_profit,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'search_query': search_query,
        'page': 'transactions',
    })

    return render(request, 'admin/transactions.html', context)

@super_admin_required
@admin_required
def admin_management(request):
    """Admin management page - Super Admin only"""
    if not is_super_admin(request.user):
        messages.error(request, 'Only Super Admins can access Admin Management.')
        return redirect('admin_dashboard')
    
    # Get all admin users (staff users)
    admin_users = User.objects.filter(is_staff=True).order_by('-date_joined')
    
    # Get permissions for each admin
    admin_list = []
    for user in admin_users:
        try:
            perms = AdminPermissions.objects.get(user=user)
        except AdminPermissions.DoesNotExist:
            # Create default permissions if none exist
            perms = AdminPermissions.objects.create(user=user)
        admin_list.append({
            'user': user,
            'permissions': perms,
            'is_superuser': user.is_superuser,
        })
    
    context = get_admin_context(request, {
        'admin_list': admin_list,
    })
    return render(request, 'admin/admin_management.html', context)

@super_admin_required
def create_admin(request):
    """Create a new admin user with permissions"""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = (request.POST.get('password2') or request.POST.get('confirm_password') or '')
        
        # Get permission checkboxes
        permissions = {
            'can_view_dashboard': request.POST.get('can_view_dashboard') == 'on',
            'can_control_dice': request.POST.get('can_control_dice') == 'on',
            'can_view_recent_rounds': request.POST.get('can_view_recent_rounds') == 'on',
            'can_view_all_bets': request.POST.get('can_view_all_bets') == 'on',
            'can_view_wallets': request.POST.get('can_view_wallets') == 'on',
            'can_view_players': request.POST.get('can_view_players') == 'on',
            'can_view_deposit_requests': request.POST.get('can_view_deposit_requests') == 'on',
            'can_view_transactions': request.POST.get('can_view_transactions') == 'on',
            'can_view_game_settings': request.POST.get('can_view_game_settings') == 'on',
            'can_view_admin_management': request.POST.get('can_view_admin_management') == 'on',
            'can_manage_payment_methods': request.POST.get('can_manage_payment_methods') == 'on',
        }
        
        # Validation
        if not username or not password:
            messages.error(request, 'Username and password are required.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions})
        
        if password != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions})

        if len(password) < 4:
            messages.error(request, 'Password must be at least 4 characters long.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions})
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions})
        
        try:
            # Create user with is_staff=True but is_superuser=False
            email = f"{username}@gundu.ata"
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True,
                is_superuser=False,
                is_active=True
            )
            
            # Create permissions
            AdminPermissions.objects.create(user=user, **permissions)
            invalidate_admin_permissions_cache(user)
            password_auto_generated = request.POST.get('password_auto_generated', 'false') == 'true'
            if password_auto_generated:
                messages.success(request, f'🎉 Admin user "{username}" created successfully! 🔐 Generated Password: <strong style="font-family: monospace; background: #f0fdf4; padding: 4px 8px; border-radius: 4px; color: #166534;">{password}</strong><br><small style="color: #666;">⚠️ Save this password securely - it will only be shown once!</small>')
            else:
                messages.success(request, f'Admin user "{username}" created successfully!')
            return redirect('admin_management')
        except Exception as e:
            messages.error(request, f'Error creating admin: {str(e)}')
            return render(request, 'admin/create_admin.html', {'permissions': permissions})
    
    return render(request, 'admin/create_admin.html', {})

@super_admin_required
def edit_admin(request, admin_id):
    """Edit admin user permissions"""
    try:
        user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Admin user not found.')
        return redirect('admin_management')
    
    # Super users cannot be edited through this interface
    if user.is_superuser:
        messages.error(request, 'Super Admin accounts cannot be edited through this interface.')
        return redirect('admin_management')
    
    # Get or create permissions
    try:
        permissions = AdminPermissions.objects.get(user=user)
    except AdminPermissions.DoesNotExist:
        permissions = AdminPermissions.objects.create(user=user)
    
    if request.method == 'POST':
        # Update permissions
        permissions.can_view_dashboard = request.POST.get('can_view_dashboard') == 'on'
        permissions.can_control_dice = request.POST.get('can_control_dice') == 'on'
        permissions.can_view_recent_rounds = request.POST.get('can_view_recent_rounds') == 'on'
        permissions.can_view_all_bets = request.POST.get('can_view_all_bets') == 'on'
        permissions.can_view_wallets = request.POST.get('can_view_wallets') == 'on'
        permissions.can_view_players = request.POST.get('can_view_players') == 'on'
        permissions.can_view_deposit_requests = request.POST.get('can_view_deposit_requests') == 'on'
        permissions.can_view_transactions = request.POST.get('can_view_transactions') == 'on'
        permissions.can_view_game_settings = request.POST.get('can_view_game_settings') == 'on'
        permissions.can_view_admin_management = request.POST.get('can_view_admin_management') == 'on'
        permissions.can_manage_payment_methods = request.POST.get('can_manage_payment_methods') == 'on'
        permissions.save()
        invalidate_admin_permissions_cache(user)
        # Update username if provided
        new_username = request.POST.get('username')
        username_updated = False
        if new_username and new_username != user.username:
            if User.objects.filter(username=new_username).exclude(id=user.id).exists():
                messages.error(request, 'Username already in use.')
            else:
                user.username = new_username
                user.save()
                username_updated = True

        # Update account status
        is_active = request.POST.get('is_active') == 'on'
        if is_active != user.is_active:
            user.is_active = is_active
            user.save()
            username_updated = True # Use this flag to trigger success message if nothing else changed

        # Update password if provided
        new_password = request.POST.get('new_password', '')
        if new_password:
            password2 = (request.POST.get('password2') or request.POST.get('confirm_password') or '')
            if new_password == password2:
                user.set_password(new_password)
                user.save()
                messages.success(request, f'Password updated for "{user.username}".')
            else:
                messages.error(request, 'Passwords do not match.')
                return redirect('admin_management')

        if username_updated or not new_password:
            messages.success(request, f'Admin "{user.username}" updated successfully!')

        return redirect('admin_management')
    
    context = get_admin_context(request, {
        'admin_user': user,
        'permissions': permissions,
    })
    return render(request, 'admin/edit_admin.html', context)

@super_admin_required
def delete_admin(request, admin_id):
    """Delete admin user and redistribute their players"""
    try:
        user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Admin user not found.')
        return redirect('admin_management')
    
    # Cannot delete superusers
    if user.is_superuser:
        messages.error(request, 'Cannot delete Super Admin accounts.')
        return redirect('admin_management')
    
    # Cannot delete yourself
    if user.id == request.user.id:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('admin_management')
    
    # Count players that will be redistributed
    player_count = User.objects.filter(worker=user, is_staff=False).count()
    username = user.username
    
    # Delete admin (signal will handle redistribution)
    user.delete()  # This will also delete AdminPermissions due to CASCADE
    
    if player_count > 0:
        messages.success(request, f'Admin user "{username}" deleted successfully! {player_count} players redistributed among remaining admins.')
    else:
        messages.success(request, f'Admin user "{username}" deleted successfully!')
    return redirect('admin_management')

@login_required(login_url='/game-admin/login/')
@admin_required
def manage_players(request):
    """Actual game players management page. Players assigned to admins only (not super admins)."""
    if not has_menu_permission(request.user, 'players'):
        messages.error(request, 'You do not have permission to view players.')
        return redirect('admin_dashboard')

    # POST: Assign unassigned players equally among admins (super admins only)
    if request.method == 'POST' and request.POST.get('action') == 'assign_unassigned':
        if not is_super_admin(request.user):
            messages.error(request, 'Only Super Admins can assign unassigned players.')
        else:
            count = redistribute_all_players()
            messages.success(request, f'Assigned {count} unassigned player(s) equally among admins.')
        return redirect('manage_players')
        
    # Get status filter from query params
    status_filter = request.GET.get('status', 'all')
    try:
        page_number = int(request.GET.get('pg', 1))
    except (ValueError, TypeError):
        page_number = 1
    search_query = request.GET.get('search', '')
    
    # Build query - only show actual players (not staff)
    users_query = User.objects.filter(is_staff=False)
    
    # If not super admin, only show assigned clients
    if not is_super_admin(request.user):
        users_query = users_query.filter(worker=request.user)
    
    # Apply status filter
    if status_filter == 'active':
        users_query = users_query.filter(is_active=True)
    elif status_filter == 'inactive':
        users_query = users_query.filter(is_active=False)
    
    # Apply search filter
    if search_query:
        users_query = users_query.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    
    # Order by joined date
    users_query = users_query.order_by('-date_joined')
    
    # Pagination
    paginator = Paginator(users_query, 20)
    try:
        page_obj = paginator.get_page(page_number)
    except Exception:
        page_obj = None
    
    # Statistics
    total_users = User.objects.filter(is_staff=False).count()
    active_users = User.objects.filter(is_staff=False, is_active=True).count()
    inactive_users = User.objects.filter(is_staff=False, is_active=False).count()
    
    # Get distribution statistics
    admins = get_admins_for_distribution()
    admin_distribution = []
    for admin in admins:
        client_count = User.objects.filter(worker=admin, is_staff=False).count()
        admin_distribution.append({
            'admin': admin,
            'client_count': client_count
        })
    admin_distribution.sort(key=lambda x: x['client_count'])
    
    # Workers dropdown: admins only (no super admins) - players are assigned to admins
    workers = get_admins_for_distribution().order_by('username')
    
    # Annotate workers with client count for display in dropdown
    for worker in workers:
        worker.client_count = User.objects.filter(worker=worker, is_staff=False).count()
    
    context = get_admin_context(request, {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'workers': workers,
        'admin_distribution': admin_distribution,
        'is_super_admin': is_super_admin(request.user),
        'page': 'manage-players',
    })
    
    return render(request, 'admin/players_list.html', context)


@login_required(login_url='/game-admin/login/')
@admin_required
def players(request):
    """Admin management page - only shows admins and super admins"""
    # Only super admins can access this page
    if not is_super_admin(request.user):
        messages.error(request, 'Only Super Admins can access admin management.')
        return redirect('admin_dashboard')

    # Get status filter from query params, default to 'active'
    status_filter = request.GET.get('status', 'active')
    try:
        page_number = int(request.GET.get('pg', 1))
    except (ValueError, TypeError):
        page_number = 1
    search_query = request.GET.get('search', '')

    # Build query - only show staff users (admins) and super admins
    users_query = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True))

    # Apply status filter - default to active
    if status_filter == 'active':
        users_query = users_query.filter(is_active=True)
    elif status_filter == 'inactive':
        users_query = users_query.filter(is_active=False)

    # Apply search filter
    if search_query:
        users_query = users_query.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )

    # Order by superuser first, then staff
    users_query = users_query.order_by('-is_superuser', '-is_staff', 'username')

    # Annotate admins with client count
    for admin in users_query:
        admin.client_count = User.objects.filter(worker=admin, is_staff=False).count()

    # Pagination
    paginator = Paginator(users_query, 20)  # 20 users per page
    try:
        page_obj = paginator.get_page(page_number)
    except Exception as e:
        page_obj = None

    # Statistics - only count admins and super admins
    total_users = users_query.count()
    active_users = users_query.filter(is_active=True).count()
    inactive_users = users_query.filter(is_active=False).count()

    context = get_admin_context(request, {
        'page_obj': page_obj,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'status_filter': status_filter,
        'search_query': search_query,
        'page': 'players',
    })

    return render(request, 'admin/players.html', context)


@login_required(login_url='/game-admin/login/')
@admin_required
def assign_worker(request):
    """Manually assign a client to an admin (super admins only). No automatic reassignment."""
    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        worker_id = request.POST.get('worker_id')
        
        if not is_super_admin(request.user):
            messages.error(request, 'Only Super Admins can assign players.')
            return redirect('manage_players')
            
        try:
            client = User.objects.get(id=client_id, is_staff=False)
            if worker_id:
                # Only allow assignment to admins (not super admins)
                admins = get_admins_for_distribution()
                worker = admins.filter(id=worker_id).first()
                if not worker:
                    messages.error(request, 'Invalid admin. Players can only be assigned to admins.')
                    return redirect('manage_players')
                client.worker = worker
                messages.success(request, f'Player {client.username} assigned to {worker.username}.')
            else:
                client.worker = None
                messages.success(request, f'Player {client.username} unassigned.')
            client.save()
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            
    return redirect('manage_players')


@login_required(login_url='/game-admin/login/')
@admin_required
def game_settings(request):
    """Game settings management page"""
    if not has_menu_permission(request.user, 'game_settings'):
        messages.error(request, 'You do not have permission to access Game Settings.')
        return redirect('admin_dashboard')
    
    from django.conf import settings as django_settings
    
    # Get or create default settings if they don't exist
    default_settings = getattr(django_settings, 'GAME_SETTINGS', {})
    
    settings_to_manage = [
        {
            'key': 'BETTING_CLOSE_TIME',
            'default': default_settings.get('BETTING_CLOSE_TIME', 30),
            'description': 'Time in seconds when betting closes (default: 30)'
        },
        {
            'key': 'DICE_ROLL_TIME',
            'default': default_settings.get('DICE_ROLL_TIME', 7),
            'description': 'Time in seconds before dice result when dice roll warning is sent (default: 7)'
        },
        {
            'key': 'DICE_RESULT_TIME',
            'default': default_settings.get('DICE_RESULT_TIME', 51),
            'description': 'Time in seconds when dice result is announced (default: 51)'
        },
        {
            'key': 'ROUND_END_TIME',
            'default': default_settings.get('ROUND_END_TIME', 80),
            'description': 'Total round duration in seconds (default: 80)'
        },
        {
            'key': 'MAX_BET',
            'default': default_settings.get('MAX_BET', 50000),
            'description': 'Maximum bet amount per number (default: 50000)'
        },
    ]

    # App version settings (for APK update prompts)
    app_version_settings = [
        {
            'key': 'APP_VERSION_CODE',
            'default': 1,
            'input_type': 'number',
            'description': 'Version code of latest APK. Bump this when you release a new APK. Users with lower versionCode will see update prompt.'
        },
        {
            'key': 'APP_VERSION_NAME',
            'default': '1.0',
            'input_type': 'text',
            'description': 'Display version name (e.g. 1.0, 1.1). Shown to users in update dialog.'
        },
        {
            'key': 'APP_DOWNLOAD_URL',
            'default': 'https://gunduata.club/gundu-ata.apk',
            'input_type': 'url',
            'description': 'Direct URL to download the latest APK. Users tap "Update" to open this link.'
        },
        {
            'key': 'APP_FORCE_UPDATE',
            'default': False,
            'input_type': 'checkbox',
            'description': 'If enabled, users MUST update to continue. They cannot dismiss the dialog.'
        },
    ]
    
    # Get current settings from database
    current_settings = {}
    for setting_info in settings_to_manage:
        try:
            setting = GameSettings.objects.get(key=setting_info['key'])
            current_settings[setting_info['key']] = {
                'value': int(setting.value),
                'description': setting.description or setting_info['description'],
                'exists': True
            }
        except GameSettings.DoesNotExist:
            current_settings[setting_info['key']] = {
                'value': setting_info['default'],
                'description': setting_info['description'],
                'exists': False
            }

    # Get current app version settings
    app_version_current = {}
    for setting_info in app_version_settings:
        try:
            setting = GameSettings.objects.get(key=setting_info['key'])
            if setting_info['input_type'] == 'number':
                val = int(setting.value)
            elif setting_info['input_type'] == 'checkbox':
                val = setting.value.lower() in ('true', '1', 'yes')
            else:
                val = setting.value
            app_version_current[setting_info['key']] = {
                'value': val,
                'description': setting.description or setting_info['description'],
                'exists': True
            }
        except (GameSettings.DoesNotExist, ValueError):
            app_version_current[setting_info['key']] = {
                'value': setting_info['default'],
                'description': setting_info['description'],
                'exists': False
            }
    
    # Handle form submission
    if request.method == 'POST':
        errors = []
        new_values = {}
        
        # First, collect and validate all values
        for setting_info in settings_to_manage:
            key = setting_info['key']
            new_value = request.POST.get(key)
            
            if new_value:
                try:
                    int_value = int(new_value)
                    if int_value < 1:
                        errors.append(f"{key.replace('_', ' ').title()} must be at least 1 second")
                        continue
                    new_values[key] = int_value
                except ValueError:
                    errors.append(f"{key.replace('_', ' ').title()} must be a valid number")
        
        # Validate relationships if all values are valid
        if not errors and len(new_values) >= 3:
            betting_close = new_values.get('BETTING_CLOSE_TIME')
            dice_roll = new_values.get('DICE_ROLL_TIME')
            dice_result = new_values.get('DICE_RESULT_TIME')
            round_end = new_values.get('ROUND_END_TIME')
            
            if betting_close and dice_result and round_end:
                if betting_close >= dice_result:
                    errors.append(f"Betting close time ({betting_close}s) must be less than dice result time ({dice_result}s)")
                if dice_result <= betting_close:
                    errors.append(f"Dice result time ({dice_result}s) must be greater than betting close time ({betting_close}s)")
                if dice_result >= round_end:
                    errors.append(f"Dice result time ({dice_result}s) must be less than round end time ({round_end}s)")
                if round_end <= dice_result:
                    errors.append(f"Round end time ({round_end}s) must be greater than dice result time ({dice_result}s)")
            
            # Validate dice roll time
            if dice_roll and dice_result:
                if dice_roll >= dice_result:
                    errors.append(f"Dice roll time ({dice_roll}s) must be less than dice result time ({dice_result}s)")
                if dice_roll < 1:
                    errors.append(f"Dice roll time ({dice_roll}s) must be at least 1 second")
        
        # If no errors, save all settings
        if not errors and new_values:
            for key, int_value in new_values.items():
                setting_info = next(s for s in settings_to_manage if s['key'] == key)
                GameSettings.objects.update_or_create(
                    key=key,
                    defaults={
                        'value': str(int_value),
                        'description': setting_info['description']
                    }
                )

            # Save app version settings
            for setting_info in app_version_settings:
                key = setting_info['key']
                if setting_info['input_type'] == 'number':
                    val = request.POST.get(key)
                    if val is not None:
                        try:
                            GameSettings.objects.update_or_create(
                                key=key,
                                defaults={
                                    'value': str(int(val)),
                                    'description': setting_info['description']
                                }
                            )
                        except ValueError:
                            pass
                elif setting_info['input_type'] == 'checkbox':
                    GameSettings.objects.update_or_create(
                        key=key,
                        defaults={
                            'value': 'true' if request.POST.get(key) == 'on' else 'false',
                            'description': setting_info['description']
                        }
                    )
                else:
                    val = request.POST.get(key)
                    if val is not None:
                        GameSettings.objects.update_or_create(
                            key=key,
                            defaults={
                                'value': val.strip(),
                                'description': setting_info['description']
                            }
                        )

            # Clear cache so app_version API returns fresh values immediately
            all_keys = [s['key'] for s in settings_to_manage] + [s['key'] for s in app_version_settings]
            clear_game_setting_cache(all_keys)

            messages.success(request, 'Game settings updated successfully! Changes will take effect for the next round only.')
            return redirect('game_settings')
        else:
            for error in errors:
                messages.error(request, error)
    
    # Prepare settings list with current values for template
    settings_list = []
    for setting_info in settings_to_manage:
        key = setting_info['key']
        setting_data = current_settings[key]
        settings_list.append({
            'key': key,
            'value': setting_data['value'],
            'description': setting_data['description'],
            'default': setting_info['default']
        })

    # Prepare app version settings list for template
    app_version_list = []
    for setting_info in app_version_settings:
        key = setting_info['key']
        setting_data = app_version_current[key]
        app_version_list.append({
            'key': key,
            'value': setting_data['value'],
            'description': setting_data['description'],
            'input_type': setting_info['input_type'],
        })
    
    # Maintenance mode status (for display in template)
    maintenance_enabled = False
    maintenance_until = None
    if getattr(settings, 'REDIS_POOL', None):
        try:
            r = redis.Redis(connection_pool=settings.REDIS_POOL)
            if r.get('maintenance_mode'):
                maintenance_enabled = True
                until_raw = r.get('maintenance_until')
                if until_raw:
                    maintenance_until = int(until_raw)
        except Exception:
            pass

    context = get_admin_context(request, {
        'settings_list': settings_list,
        'app_version_list': app_version_list,
        'maintenance_enabled': maintenance_enabled,
        'maintenance_until': maintenance_until,
        'page': 'game_settings',
        'admin_profile': get_admin_profile(request.user),
    })

    return render(request, 'admin/game_settings.html', context)


@login_required(login_url='/game-admin/login/')
@admin_required
def help_center(request):
    """Help Center settings (WhatsApp + Telegram phone number)"""
    # Treat as a settings page: require game_settings permission
    if not has_menu_permission(request.user, 'game_settings'):
        messages.error(request, 'You do not have permission to access Help Center settings.')
        return redirect('admin_dashboard')

    # Current values (GameSettings-backed, cached via get_game_setting)
    whatsapp_number = get_game_setting('SUPPORT_WHATSAPP_NUMBER', '')
    telegram_number = get_game_setting('SUPPORT_TELEGRAM', '')

    def normalize_phone_number(raw: str) -> str:
        """
        Keep leading '+' (if provided) and digits only; remove spaces/dashes/etc.
        Accepts any country code (e.g. +91, +231).
        """
        if raw is None:
            return ''
        s = str(raw).strip()
        if not s:
            return ''
        keep_plus = s.startswith('+')
        digits = ''.join(ch for ch in s if ch.isdigit())
        if not digits:
            return ''
        return f"+{digits}" if keep_plus else digits

    if request.method == 'POST':
        whatsapp_number = normalize_phone_number(request.POST.get('SUPPORT_WHATSAPP_NUMBER'))
        telegram_number = normalize_phone_number(request.POST.get('SUPPORT_TELEGRAM'))

        GameSettings.objects.update_or_create(
            key='SUPPORT_WHATSAPP_NUMBER',
            defaults={
                'value': whatsapp_number,
                'description': 'Help Center WhatsApp number (example: +919876543210)'
            }
        )
        GameSettings.objects.update_or_create(
            key='SUPPORT_TELEGRAM',
            defaults={
                'value': telegram_number,
                'description': 'Help Center Telegram phone number (example: +919876543210)'
            }
        )

        clear_game_setting_cache(['SUPPORT_WHATSAPP_NUMBER', 'SUPPORT_TELEGRAM'])
        messages.success(request, 'Help Center contacts updated successfully.')
        return redirect('help_center')

    context = get_admin_context(request, {
        'page': 'help_center',
        'whatsapp_number': whatsapp_number,
        'telegram_number': telegram_number,
        'admin_profile': get_admin_profile(request.user),
    })
    return render(request, 'admin/help_center.html', context)


@login_required(login_url='/game-admin/login/')
@admin_required
def white_label_leads(request):
    """List White Label lead submissions"""
    # Treat as a settings page: require game_settings permission
    if not has_menu_permission(request.user, 'game_settings'):
        messages.error(request, 'You do not have permission to access White Label leads.')
        return redirect('admin_dashboard')

    q = (request.GET.get('q') or '').strip()
    leads_qs = WhiteLabelLead.objects.all()
    if q:
        leads_qs = leads_qs.filter(
            Q(name__icontains=q) |
            Q(phone_number__icontains=q) |
            Q(message__icontains=q)
        )

    paginator = Paginator(leads_qs, 50)
    leads_page = paginator.get_page(request.GET.get('p') or 1)

    context = get_admin_context(request, {
        'page': 'white_label',
        'admin_profile': get_admin_profile(request.user),
        'q': q,
        'leads_page': leads_page,
        'total_count': leads_qs.count(),
    })
    return render(request, 'admin/white_label_leads.html', context)


@login_required(login_url='/game-admin/login/')
@admin_required
def maintenance_toggle(request):
    """Enable or disable maintenance mode from admin panel. Requires game_settings permission."""
    if not has_menu_permission(request.user, 'game_settings'):
        messages.error(request, 'You do not have permission to manage maintenance.')
        return redirect('admin_dashboard')

    import time
    r = None
    if getattr(settings, 'REDIS_POOL', None):
        r = redis.Redis(connection_pool=settings.REDIS_POOL)

    if request.method == 'POST':
        action = request.POST.get('maintenance_action')
        if action == 'enable':
            duration_minutes = request.POST.get('maintenance_duration', '30')
            try:
                mins = int(duration_minutes)
                if mins < 1:
                    mins = 30
                elif mins > 480:  # max 8 hours
                    mins = 480
            except (ValueError, TypeError):
                mins = 30
            if r:
                now = int(time.time())
                until = now + (mins * 60)
                r.set('maintenance_mode', '1')
                r.set('maintenance_until', str(until))
                # Auto-disable after that time: Redis expires the key so maintenance ends even with no traffic
                r.expireat('maintenance_mode', until)
                r.expireat('maintenance_until', until)
                messages.success(request, f'Maintenance enabled for {mins} minutes. It will automatically turn off after that time.')
            else:
                messages.error(request, 'Redis not configured. Set MAINTENANCE_MODE=1 in environment instead.')
        elif action == 'disable':
            if r:
                r.delete('maintenance_mode')
                r.delete('maintenance_until')
                messages.success(request, 'Maintenance mode disabled. App is live again.')
            else:
                messages.error(request, 'Redis not configured. Unset MAINTENANCE_MODE in environment.')

    return redirect('game_settings')


@login_required(login_url='/game-admin/login/')
@require_POST
def logout_all_sessions(request):
    """Log out all users: invalidate all JWT (app) and clear all Django sessions (game-admin). Superuser only."""
    if not request.user.is_superuser:
        messages.error(request, 'Only superusers can log out all users.')
        return redirect('admin_dashboard')
    if not has_menu_permission(request.user, 'game_settings'):
        messages.error(request, 'You do not have permission to manage this.')
        return redirect('admin_dashboard')

    import time
    now = int(time.time())
    r = None
    if getattr(settings, 'REDIS_POOL', None):
        r = redis.Redis(connection_pool=settings.REDIS_POOL)

    # Invalidate all JWT (app users)
    if r:
        r.set('logout_all_issued_before', str(now))
        try:
            keys = list(r.scan_iter('user_session:*', count=1000))
            if keys:
                r.delete(*keys)
        except Exception:
            pass

    # Clear all Django sessions (game-admin users; you will be logged out too)
    count, _ = Session.objects.all().delete()

    messages.success(request, f'All users have been logged out. ({count} game-admin session(s) cleared; app users must log in again.)')
    return redirect('admin_login')


@admin_required
def payment_methods(request):
    """List all payment methods"""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    # Create default payment methods if none exist
    if not PaymentMethod.objects.exists():
        default_methods = [
            {
                'name': 'Bank Account',
                'method_type': 'BANK',
                'is_active': True,
                'usdt_network': '',
                'usdt_wallet_address': '',
            },
            {
                'name': 'Google Pay',
                'method_type': 'GPAY',
                'is_active': True,
                'usdt_network': '',
                'usdt_wallet_address': '',
            },
            {
                'name': 'Phone Pe',
                'method_type': 'PHONEPE',
                'is_active': True,
                'usdt_network': '',
                'usdt_wallet_address': '',
            },
            {
                'name': 'Paytm',
                'method_type': 'PAYTM',
                'is_active': True,
                'usdt_network': '',
                'usdt_wallet_address': '',
            },
            {
                'name': 'UPI',
                'method_type': 'UPI',
                'is_active': True,
                'usdt_network': '',
                'usdt_wallet_address': '',
            },
            {
                'name': 'QR',
                'method_type': 'QR',
                'is_active': True,
                'usdt_network': '',
                'usdt_wallet_address': '',
            },
        ]

        for method_data in default_methods:
            PaymentMethod.objects.create(**method_data)

        messages.info(request, 'Created default payment methods. Please edit them with your actual payment details.')

    methods = PaymentMethod.objects.all().order_by('-is_active', 'method_type')

    # Get available method types (exclude already used ones)
    used_method_types = set(methods.values_list('method_type', flat=True))
    all_method_choices = PaymentMethod.METHOD_TYPES

    # Filter out already used method types
    available_method_types = [mt for mt in all_method_choices if mt[0] not in used_method_types]

    context = get_admin_context(request, {
        'payment_methods': methods,
        'available_method_types': available_method_types,
        'page': 'payment-methods',
    })
    return render(request, 'admin/payment_methods.html', context)

@admin_required
def create_payment_method(request):
    """Create a new payment method"""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    if request.method == 'POST':
        method_type = request.POST.get('method_type')
        upi_id = request.POST.get('upi_id', '')
        link = request.POST.get('link', '')
        account_name = request.POST.get('account_name', '')
        bank_name = request.POST.get('bank_name', '')
        account_number = request.POST.get('account_number', '')
        ifsc_code = request.POST.get('ifsc_code', '')
        qr_image = request.FILES.get('qr_image')
        is_active = request.POST.get('is_active') == 'on'
        usdt_network = request.POST.get('usdt_network', '') or ''
        usdt_wallet_address = request.POST.get('usdt_wallet_address', '') or ''
        usdt_exchange_rate = request.POST.get('usdt_exchange_rate', '90.00')
        if not usdt_exchange_rate or usdt_exchange_rate.strip() == '':
            usdt_exchange_rate = '90.00'

        if not method_type:
            messages.error(request, 'Method Type is required.')
            return redirect('payment_methods')

        # Check if this method type is already used
        if PaymentMethod.objects.filter(method_type=method_type).exists():
            messages.error(request, 'This payment method type is already in use.')
            return redirect('payment_methods')

        # Get the display name for the method type
        method_type_display = dict(PaymentMethod.METHOD_TYPES).get(method_type, method_type)

        try:
            # Clean exchange rate - remove any non-numeric characters except decimal point
            import re
            clean_rate = re.sub(r'[^\d.]', '', str(usdt_exchange_rate))
            if not clean_rate or clean_rate == '.':
                clean_rate = '90.00'
            
            PaymentMethod.objects.create(
                name=method_type_display,
                method_type=method_type,
                upi_id=upi_id,
                link=link,
                account_name=account_name,
                bank_name=bank_name,
                account_number=account_number,
                ifsc_code=ifsc_code,
                qr_image=qr_image,
                is_active=is_active,
                usdt_network=usdt_network,
                usdt_wallet_address=usdt_wallet_address,
                usdt_exchange_rate=Decimal(clean_rate)
            )
            messages.success(request, f'Payment method "{method_type_display}" created successfully!')
        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f'Error creating payment method: {str(e)}')

    return redirect('payment_methods')

@admin_required
def edit_payment_method(request, pk):
    """Edit a payment method"""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    method = get_object_or_404(PaymentMethod, pk=pk)

    if request.method == 'POST':
        method.method_type = request.POST.get('method_type')
        method.upi_id = request.POST.get('upi_id', '')
        method.link = request.POST.get('link', '')
        method.account_name = request.POST.get('account_name', '')
        method.bank_name = request.POST.get('bank_name', '')
        method.account_number = request.POST.get('account_number', '')
        method.ifsc_code = request.POST.get('ifsc_code', '')

        # Handle QR image upload
        if 'qr_image' in request.FILES:
            method.qr_image = request.FILES['qr_image']

        method.is_active = request.POST.get('is_active') == 'on'
        method.usdt_network = request.POST.get('usdt_network', '')
        method.usdt_wallet_address = request.POST.get('usdt_wallet_address', '')
        
        exchange_rate = request.POST.get('usdt_exchange_rate')
        if exchange_rate:
            try:
                method.usdt_exchange_rate = Decimal(exchange_rate)
            except (InvalidOperation, ValueError):
                pass

        if not method.method_type:
            messages.error(request, 'Method Type is required.')
        else:
            # Update the name based on method type
            method.name = dict(PaymentMethod.METHOD_TYPES).get(method.method_type, method.method_type)

            try:
                method.save()
                messages.success(request, f'Payment method "{method.name}" updated successfully!')
            except Exception as e:
                messages.error(request, f'Error updating payment method: {str(e)}')

    return redirect('payment_methods')

@admin_required
def delete_payment_method(request, pk):
    """Delete a payment method"""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    if request.method == 'POST':
        method = get_object_or_404(PaymentMethod, pk=pk)
        name = method.name

        try:
            method.delete()
            messages.success(request, f'Payment method "{name}" deleted successfully!')
        except Exception as e:
            messages.error(request, f'Error deleting payment method: {str(e)}')

    return redirect('payment_methods')


@admin_required
def toggle_payment_method(request, pk):
    """Toggle active status of a payment method"""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')
    
    method = get_object_or_404(PaymentMethod, pk=pk)
    method.is_active = not method.is_active
    method.save()
    
    status = "activated" if method.is_active else "deactivated"
    messages.success(request, f'Payment method "{method.name}" {status} successfully!')
    return redirect('payment_methods')
