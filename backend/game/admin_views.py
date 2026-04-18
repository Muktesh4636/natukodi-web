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
from .models import GameRound, Bet, DiceResult, GameSettings, AdminPermissions, WhiteLabelLead, LiveStream, CricketBet, CockFightBet
from accounts.models import (
    Wallet,
    Transaction,
    DepositRequest,
    WithdrawRequest,
    User,
    PaymentMethod,
    FranchiseBalance,
    FranchiseBalanceLog,
    deposit_payment_reference_in_use,
)
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
    get_effective_admin,
)
from .utils import get_game_setting, clear_game_setting_cache
from .load_test_utils import load_tester
from decimal import Decimal, InvalidOperation
import decimal
from django.core.paginator import Paginator
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

# Dashboard "daily" metrics are requested in IST (business day).
# We keep project TIME_ZONE=UTC, so compute IST day bounds and convert to UTC for DB filtering.
import datetime as _dt
_IST_TZ = _dt.timezone(_dt.timedelta(hours=5, minutes=30))


def _ist_day_bounds_utc(day_offset: int = 0):
    """
    Return (start_utc, end_utc, ist_date) for IST day `today + day_offset`.
    Uses a fixed +05:30 offset (no DST in IST).
    """
    now_ist = timezone.now().astimezone(_IST_TZ)
    ist_date = now_ist.date() + _dt.timedelta(days=day_offset)
    start_ist = _dt.datetime.combine(ist_date, _dt.time.min, tzinfo=_IST_TZ)
    end_ist = start_ist + _dt.timedelta(days=1)
    return start_ist.astimezone(_dt.timezone.utc), end_ist.astimezone(_dt.timezone.utc), ist_date


# Cache TTLs for admin dashboard (reduce DB load and avoid 504 timeouts)
ADMIN_DASHBOARD_STATS_CACHE_KEY = 'admin_dashboard_bet_stats'
ADMIN_DASHBOARD_STATS_TTL = 300  # 5 min - heavy Bet aggregate runs at most once per 5 min
ADMIN_DASHBOARD_STATS_FRANCHISE_PREFIX = 'admin_dashboard_bet_stats_franchise_'  # + admin_id
ADMIN_DASHBOARD_STATS_FRANCHISE_TTL = 90   # seconds - franchise stats cached to avoid slow page loads
ADMIN_DASHBOARD_DATA_CACHE_KEY = 'admin_dashboard_data_json_v6'
ADMIN_DASHBOARD_DATA_TTL = 20   # seconds - dashboard-data returns cache more often
# Dashboard shows daily overview only (today's stats)
ADMIN_DASHBOARD_STATS_DAYS = 1
# Cache for sidebar "worker management" check so we don't hit DB on every admin page load
ADMIN_WORKER_MGMT_CACHE_PREFIX = 'admin_worker_mgmt_'
ADMIN_WORKER_MGMT_CACHE_TTL = 60

# Redis connection using connection pool (optimized for scalability)
from .utils import get_redis_client

# Redis connection with tiered failover
redis_client = get_redis_client()

# Health dashboard cache (avoid expensive full API scans on every page refresh)
SYSTEM_HEALTH_CACHE_KEY = 'admin_system_health_snapshot'
SYSTEM_HEALTH_CACHE_TTL = 20


def _iter_urlpatterns(patterns, prefix=''):
    from django.urls import URLPattern, URLResolver

    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            nested_prefix = prefix + str(pattern.pattern)
            yield from _iter_urlpatterns(pattern.url_patterns, nested_prefix)
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern.name


def _materialize_api_path(route):
    import re

    path = route
    path = re.sub(r'<int:[^>]+>', '1', path)
    path = re.sub(r'<str:[^>]+>', 'sample', path)
    path = re.sub(r'<slug:[^>]+>', 'sample-slug', path)
    path = re.sub(r'<uuid:[^>]+>', '123e4567-e89b-12d3-a456-426614174000', path)
    path = '/' + path.lstrip('^').lstrip('/')
    path = path.replace('\\Z', '').replace('$', '')
    return path


def _discover_api_paths():
    from django.urls import get_resolver

    resolver = get_resolver()
    discovered = []
    seen = set()
    for route, _ in _iter_urlpatterns(resolver.url_patterns):
        path = _materialize_api_path(route)
        # Skip regex catch-all/static paths we cannot safely probe.
        if '(?!' in path or '(?P<' in path or '.*' in path:
            continue
        if not (path.startswith('/api/') or path.startswith('/webgl/api/')):
            continue
        if path not in seen:
            discovered.append(path)
            seen.add(path)
    return discovered


def _run_api_health_checks(request):
    import time
    from django.test import Client

    start = time.perf_counter()
    host = (request.get_host() or 'localhost').split(',')[0].strip() or 'localhost'
    client = Client(HTTP_HOST=host)

    routes = _discover_api_paths()
    checks = []
    failed = 0
    warning = 0
    healthy = 0

    for path in routes:
        route_start = time.perf_counter()
        status_code = None
        error = None
        try:
            response = client.get(path)
            status_code = response.status_code
        except Exception as exc:
            error = str(exc)

        elapsed_ms = round((time.perf_counter() - route_start) * 1000, 2)

        if error:
            state = 'failed'
            failed += 1
        elif status_code >= 500:
            state = 'failed'
            failed += 1
        elif status_code >= 400:
            state = 'warning'
            warning += 1
        else:
            state = 'healthy'
            healthy += 1

        checks.append({
            'path': path,
            'status_code': status_code,
            'state': state,
            'error': error,
            'response_ms': elapsed_ms,
        })

    total_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        'total_routes': len(routes),
        'healthy': healthy,
        'warning': warning,
        'failed': failed,
        'duration_ms': total_ms,
        'checks': checks,
    }


def _run_websocket_health_checks():
    import time
    from asgiref.sync import async_to_sync

    checks = []

    route_start = time.perf_counter()
    try:
        from game.routing import websocket_urlpatterns
        route_names = [str(pattern.pattern) for pattern in websocket_urlpatterns]
        has_primary_route = any('ws/game' in route for route in route_names)
        checks.append({
            'name': 'WebSocket route mapping',
            'state': 'healthy' if has_primary_route else 'failed',
            'detail': ', '.join(route_names) if route_names else 'No websocket routes configured.',
            'response_ms': round((time.perf_counter() - route_start) * 1000, 2),
        })
    except Exception as exc:
        checks.append({
            'name': 'WebSocket route mapping',
            'state': 'failed',
            'detail': str(exc),
            'response_ms': round((time.perf_counter() - route_start) * 1000, 2),
        })

    layer_start = time.perf_counter()
    try:
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            raise RuntimeError('Channel layer unavailable.')

        channel_name = async_to_sync(channel_layer.new_channel)('health.dashboard.')
        payload = {'type': 'health.ping', 'value': 'ok'}
        async_to_sync(channel_layer.send)(channel_name, payload)
        received = async_to_sync(channel_layer.receive)(channel_name)
        if received.get('value') != 'ok':
            raise RuntimeError('Unexpected channel-layer payload.')

        checks.append({
            'name': 'Channel layer round-trip',
            'state': 'healthy',
            'detail': 'Send/receive check passed.',
            'response_ms': round((time.perf_counter() - layer_start) * 1000, 2),
        })
    except Exception as exc:
        checks.append({
            'name': 'Channel layer round-trip',
            'state': 'failed',
            'detail': str(exc),
            'response_ms': round((time.perf_counter() - layer_start) * 1000, 2),
        })

    redis_start = time.perf_counter()
    try:
        ws_redis_client = get_redis_client()
        if ws_redis_client:
            ws_redis_client.ping()
            checks.append({
                'name': 'Redis connectivity (WS dependency)',
                'state': 'healthy',
                'detail': 'Redis ping succeeded.',
                'response_ms': round((time.perf_counter() - redis_start) * 1000, 2),
            })
        else:
            checks.append({
                'name': 'Redis connectivity (WS dependency)',
                'state': 'warning',
                'detail': 'Redis client unavailable; WS may still work with in-memory layer.',
                'response_ms': round((time.perf_counter() - redis_start) * 1000, 2),
            })
    except Exception as exc:
        checks.append({
            'name': 'Redis connectivity (WS dependency)',
            'state': 'failed',
            'detail': str(exc),
            'response_ms': round((time.perf_counter() - redis_start) * 1000, 2),
        })

    return checks


def _collect_system_health_snapshot(request):
    api_section = _run_api_health_checks(request)
    websocket_checks = _run_websocket_health_checks()
    websocket_failed = sum(1 for item in websocket_checks if item['state'] == 'failed')
    websocket_warning = sum(1 for item in websocket_checks if item['state'] == 'warning')
    websocket_healthy = sum(1 for item in websocket_checks if item['state'] == 'healthy')
    now_iso = timezone.now().isoformat()

    return {
        'generated_at': now_iso,
        'api': api_section,
        'websocket': {
            'total_checks': len(websocket_checks),
            'healthy': websocket_healthy,
            'warning': websocket_warning,
            'failed': websocket_failed,
            'checks': websocket_checks,
        },
    }


def system_health_data(request):
    refresh = request.GET.get('refresh') == '1'
    snapshot = None if refresh else cache.get(SYSTEM_HEALTH_CACHE_KEY)
    if snapshot is None:
        snapshot = _collect_system_health_snapshot(request)
        try:
            cache.set(SYSTEM_HEALTH_CACHE_KEY, snapshot, SYSTEM_HEALTH_CACHE_TTL)
        except Exception:
            pass
    return JsonResponse(snapshot, status=200)


def system_health_dashboard(request):
    snapshot = cache.get(SYSTEM_HEALTH_CACHE_KEY)
    if snapshot is None:
        snapshot = _collect_system_health_snapshot(request)
        try:
            cache.set(SYSTEM_HEALTH_CACHE_KEY, snapshot, SYSTEM_HEALTH_CACHE_TTL)
        except Exception:
            pass

    return render(request, 'system_health.html', {
        'health_snapshot': snapshot,
    })

def get_admin_context(request, extra_context=None):
    """Helper function to get common admin context for all admin pages"""
    admin_permissions = get_admin_permissions(request.user)

    class DummyPermissions:
        def __init__(self, all_true=False):
            for attr in (
                'can_view_dashboard', 'can_control_dice', 'can_view_recent_rounds', 'can_view_all_bets',
                'can_view_wallets', 'can_view_players', 'can_view_deposit_requests', 'can_view_withdraw_requests',
                'can_view_transactions', 'can_view_game_history', 'can_view_game_settings',
                'can_view_admin_management', 'can_manage_payment_methods', 'can_view_help_center', 'can_view_white_label',
            ):
                setattr(self, attr, all_true)

    # Ensure template never sees None: super admin gets all True; others get all False if perms missing
    if admin_permissions is None:
        admin_permissions = DummyPermissions(all_true=is_super_admin(request.user))

    # Franchise owners always get Worker Management menu (they manage workers under them). Cache to avoid DB on every page.
    cache_key = ADMIN_WORKER_MGMT_CACHE_PREFIX + str(request.user.id)
    can_access_worker_management = cache.get(cache_key)
    if can_access_worker_management is None:
        can_access_worker_management = (
            is_super_admin(request.user)
            or (admin_permissions and getattr(admin_permissions, 'can_view_admin_management', False))
            or getattr(request.user, 'is_franchise_only', False)
            or (FranchiseBalance.objects.filter(user=request.user).exists() and not getattr(request.user, 'works_under_id', None))
        )
        try:
            cache.set(cache_key, can_access_worker_management, ADMIN_WORKER_MGMT_CACHE_TTL)
        except Exception:
            pass
    context = {
        'admin_permissions': admin_permissions,
        'is_super_admin': is_super_admin(request.user),
        'user': request.user,
        'user_works_under_id': getattr(request.user, 'works_under_id', None) or '',
        'can_access_worker_management': can_access_worker_management,
    }
    
    if extra_context:
        context.update(extra_context)
    
    return context


def _increment_admin_login_fails(cache, failed_attempts_key, lockout_until_key, lockout_cycle_key,
                                 attempts_before_lockout, first_lockout_seconds, max_lockout_seconds):
    """Increment failed-attempt count; if >= attempts_before_lockout, set lockout (30s, 60s, 120s, ... doubling, cap at max).
    Returns lockout message string if lockout was applied, else None. Swallows cache errors to avoid 500."""
    import time
    try:
        fails = cache.get(failed_attempts_key, 0) + 1
        cache.set(failed_attempts_key, fails, 3600)
        if fails < attempts_before_lockout:
            return None
        cycle = cache.get(lockout_cycle_key, 0) or 0
        duration = min(first_lockout_seconds * (2 ** int(cycle)), max_lockout_seconds)
        cache.set(lockout_cycle_key, cycle + 1, 7200)
        cache.set(lockout_until_key, time.time() + duration, int(duration) + 60)
        cache.delete(failed_attempts_key)
        return f'Too many failed attempts. Please wait {int(duration)} seconds before trying again.'
    except Exception as e:
        logger.warning('admin_login lockout/cache: %s', e)
        return None


def admin_ping(request):
    """No-auth health check for /game-admin/ routing. Returns 200 if Django is reachable."""
    from django.http import JsonResponse
    return JsonResponse({'ok': True, 'message': 'game-admin reachable'}, status=200)


@ensure_csrf_cookie
@csrf_exempt
def admin_login(request):
    """Custom login page for game admin panel - SECURITY: Progressive lockout (4 tries, then 30s/60s/120s...)"""
    if request.user.is_authenticated and is_admin(request.user):
        # Already logged in and is admin, redirect to dashboard
        next_url = request.GET.get('next', '/game-admin/dashboard/')
        return redirect(next_url)
    
    # SECURITY: Progressive lockout — 4 wrong attempts then wait (30s, then 60s, then 120s, doubling each time)
    import time
    from django.core.cache import cache
    from django.conf import settings

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0].strip()
    else:
        client_ip = request.META.get('REMOTE_ADDR', '')

    failed_attempts_key = f'admin_login_fails_{client_ip}'
    lockout_until_key = f'admin_login_lockout_until_{client_ip}'
    lockout_cycle_key = f'admin_login_lockout_cycle_{client_ip}'

    ATTEMPTS_BEFORE_LOCKOUT = 4
    FIRST_LOCKOUT_SECONDS = 30
    MAX_LOCKOUT_SECONDS = 900  # cap at 15 minutes

    now = time.time()
    try:
        lockout_until = cache.get(lockout_until_key)
    except Exception:
        lockout_until = None
    if lockout_until is not None:
        try:
            lockout_until = float(lockout_until)
        except (TypeError, ValueError):
            lockout_until = None
    if lockout_until is not None and now < lockout_until:
        seconds_left = max(1, int(lockout_until - now) + 1)
        context = {
            'next': request.GET.get('next', '/game-admin/dashboard/'),
            'error_message': f'Too many failed attempts. Please wait {seconds_left} seconds before trying again.',
        }
        return render(request, 'admin/login.html', context)

    error_message = None
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = (request.POST.get('password') or '').strip()
        next_url = request.POST.get('next', '/game-admin/dashboard/')
        
        if username and password:
            from django.contrib.auth import authenticate, login
            user = authenticate(request, username=username, password=password)
            # If exact username failed, try case-insensitive lookup (e.g. "Sai" vs "sai")
            if user is None and username:
                try:
                    u = User.objects.get(username__iexact=username)
                    if u.check_password(password):
                        user = u
                except User.DoesNotExist:
                    pass
            if user is not None:
                if not user.is_active:
                    error_message = 'This account is deactivated. Contact an administrator.'
                elif is_admin(user):
                    # Successful login - reset lockout and fail counters
                    cache.delete(failed_attempts_key)
                    cache.delete(lockout_until_key)
                    cache.delete(lockout_cycle_key)
                    login(request, user)
                    request.session.save()
                    messages.success(request, f'Welcome, {user.username}!')
                    # Render dashboard in same request so session cookie is in this response (avoids redirect cookie loss)
                    try:
                        return admin_dashboard(request)
                    except Exception as e:
                        logger.exception('admin_dashboard after login: %s', e)
                        # Fallback: redirect so user still gets session cookie; next request may succeed
                        return redirect('/game-admin/dashboard/')
                else:
                    error_message = 'You do not have permission to access the admin panel.'
                    lockout_msg = _increment_admin_login_fails(cache, failed_attempts_key, lockout_until_key, lockout_cycle_key,
                                                               ATTEMPTS_BEFORE_LOCKOUT, FIRST_LOCKOUT_SECONDS, MAX_LOCKOUT_SECONDS)
                    if lockout_msg:
                        error_message = lockout_msg
            else:
                error_message = 'Invalid username or password.'
                lockout_msg = _increment_admin_login_fails(cache, failed_attempts_key, lockout_until_key, lockout_cycle_key,
                                                          ATTEMPTS_BEFORE_LOCKOUT, FIRST_LOCKOUT_SECONDS, MAX_LOCKOUT_SECONDS)
                if lockout_msg:
                    error_message = lockout_msg
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


def admin_forgot_password(request):
    """Forgot password page: instructs admin users to contact Super Admin to reset password."""
    return render(request, 'admin/forgot_password.html', {})


@admin_required
def admin_profile(request):
    """Profile page for the logged-in admin: view info and change password."""
    user = request.user
    is_franchise_owner = getattr(user, 'is_franchise_only', False) or (
        FranchiseBalance.objects.filter(user=user).exists() and not getattr(user, 'works_under_id', None)
    )
    role_label = 'Super Admin' if user.is_superuser else ('Franchise owner' if is_franchise_owner else 'Worker')
    if request.method == 'POST' and request.POST.get('action') == 'change_password':
        if user.is_superuser:
            messages.error(request, 'Super Admin password cannot be changed from this page.')
        else:
            new_password = (request.POST.get('new_password') or '').strip()
            new_password_confirm = (request.POST.get('new_password_confirm') or '').strip()
            if not new_password:
                messages.error(request, 'New password is required.')
            elif len(new_password) < 4:
                messages.error(request, 'Password must be at least 4 characters.')
            elif new_password != new_password_confirm:
                messages.error(request, 'Passwords do not match.')
            else:
                user.set_password(new_password)
                user.save()
                messages.success(request, 'Your password has been updated.')
        return redirect('admin_profile')
    context = get_admin_context(request, {
        'page': 'profile',
        'profile_user': user,
        'role_label': role_label,
    })
    return render(request, 'admin/profile.html', context)


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
    effective_admin = get_effective_admin(request.user)

    # Dashboard template only shows franchise chips + games overview (JSON from admin_dashboard_data).
    my_franchise_balance = None
    my_franchise_balance_display = ''
    try:
        if not is_super_admin(effective_admin):
            try:
                fb = FranchiseBalance.objects.get(user=effective_admin)
                my_franchise_balance = fb.balance
            except FranchiseBalance.DoesNotExist:
                my_franchise_balance = 0
            from .utils import format_indian_int
            my_franchise_balance_display = format_indian_int(my_franchise_balance)
    except Exception as e:
        logger.warning('admin_dashboard franchise balance: %s', e)

    context = get_admin_context(request, {
        'page': 'dashboard',
        'admin_profile': admin_profile,
        'my_franchise_balance': my_franchise_balance,
        'my_franchise_balance_display': my_franchise_balance_display,
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
    """API endpoint to get admin dashboard data. Franchise owners see only their players' stats."""
    from django.http import HttpResponse
    effective_admin = get_effective_admin(request.user)
    # Only super admin uses shared cache; franchise gets fresh scoped data
    cached = None
    if is_super_admin(effective_admin):
        cached = cache.get(ADMIN_DASHBOARD_DATA_CACHE_KEY)
    if cached is not None:
        return HttpResponse(cached, content_type='application/json')

    def _scope_bet(qs):
        return qs.filter(user__worker=effective_admin) if not is_super_admin(effective_admin) else qs
    def _scope_txn(qs):
        return qs.filter(user__worker=effective_admin) if not is_super_admin(effective_admin) else qs
    def _scope_user(qs):
        return qs.filter(worker=effective_admin) if not is_super_admin(effective_admin) else qs

    # Get current round state using helper (fast: Redis + one GameRound lookup)
    from .utils import get_current_round_state
    try:
        current_round, timer, status, _ = get_current_round_state(redis_client)
    except Exception as e:
        logger.warning('admin_dashboard_data get_current_round_state: %s', e)
        current_round, timer, status = None, 0, 'WAITING'

    # Overall stats: franchise-scoped when not super admin
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=ADMIN_DASHBOARD_STATS_DAYS)
    bet_base = Bet.objects.filter(created_at__gte=cutoff)
    if is_super_admin(effective_admin):
        bet_stats = cache.get(ADMIN_DASHBOARD_STATS_CACHE_KEY)
        if bet_stats is None:
            bet_stats = bet_base.aggregate(total_bets=Count('id'), total_amount=Sum('chip_amount'), total_payout=Sum('payout_amount'))
            try:
                cache.set(ADMIN_DASHBOARD_STATS_CACHE_KEY, bet_stats, ADMIN_DASHBOARD_STATS_TTL)
            except Exception:
                pass
    else:
        bet_stats = _scope_bet(bet_base).aggregate(total_bets=Count('id'), total_amount=Sum('chip_amount'), total_payout=Sum('payout_amount'))
    overall_total_amount = bet_stats.get('total_amount') or 0
    overall_total_payout = bet_stats.get('total_payout') or 0
    overall_total_profit = (overall_total_amount or 0) - (overall_total_payout or 0)
    total_bets_count = bet_stats.get('total_bets') or 0

    # Daily data (IST)
    today_start_utc, today_end_utc, today_ist_date = _ist_day_bounds_utc(0)
    yday_start_utc, yday_end_utc, yday_ist_date = _ist_day_bounds_utc(-1)

    today_bet_agg = _scope_bet(Bet.objects.filter(created_at__gte=today_start_utc, created_at__lt=today_end_utc)).aggregate(
        bets_count=Count('id'), bets_amount=Sum('chip_amount'), payout_amount=Sum('payout_amount'),
    )
    yday_bet_agg = _scope_bet(Bet.objects.filter(created_at__gte=yday_start_utc, created_at__lt=yday_end_utc)).aggregate(
        bets_count=Count('id'), bets_amount=Sum('chip_amount'), payout_amount=Sum('payout_amount'),
    )
    today_deposit_agg = _scope_txn(Transaction.objects.filter(
        created_at__gte=today_start_utc, created_at__lt=today_end_utc, transaction_type='DEPOSIT'
    )).aggregate(count=Count('id'), amount=Sum('amount'))
    today_withdraw_agg = _scope_txn(Transaction.objects.filter(
        created_at__gte=today_start_utc, created_at__lt=today_end_utc, transaction_type='WITHDRAW'
    )).aggregate(count=Count('id'), amount=Sum('amount'))
    yday_deposit_agg = _scope_txn(Transaction.objects.filter(
        created_at__gte=yday_start_utc, created_at__lt=yday_end_utc, transaction_type='DEPOSIT'
    )).aggregate(count=Count('id'), amount=Sum('amount'))
    yday_withdraw_agg = _scope_txn(Transaction.objects.filter(
        created_at__gte=yday_start_utc, created_at__lt=yday_end_utc, transaction_type='WITHDRAW'
    )).aggregate(count=Count('id'), amount=Sum('amount'))

    today_active_bettors = _scope_bet(Bet.objects.filter(created_at__gte=today_start_utc, created_at__lt=today_end_utc)).aggregate(n=Count('user_id', distinct=True))['n'] or 0
    yday_active_bettors = _scope_bet(Bet.objects.filter(created_at__gte=yday_start_utc, created_at__lt=yday_end_utc)).aggregate(n=Count('user_id', distinct=True))['n'] or 0

    today_new_users = _scope_user(User.objects.filter(is_staff=False, created_at__gte=today_start_utc, created_at__lt=today_end_utc)).count()
    yday_new_users = _scope_user(User.objects.filter(is_staff=False, created_at__gte=yday_start_utc, created_at__lt=yday_end_utc)).count()

    # Per-game aggregates (API + dashboard three-card overview)
    period_days = 90
    period_start_utc = timezone.now() - _dt.timedelta(days=period_days)

    def _scope_cricket_cf(qs):
        if is_super_admin(effective_admin):
            return qs
        return qs.filter(user__worker=effective_admin)

    def _bet_metric_block(qs):
        agg = qs.aggregate(
            bets_count=Count('id'),
            stake_amount=Sum('chip_amount'),
            payout_amount=Sum('payout_amount'),
        )
        stake = float(agg.get('stake_amount') or 0)
        payout = float(agg.get('payout_amount') or 0)
        return {
            'bets_count': int(agg.get('bets_count') or 0),
            'stake_amount': stake,
            'payout_amount': payout,
            'profit': stake - payout,
        }

    def _cricket_cf_metric_block(qs):
        agg = qs.aggregate(
            bets_count=Count('id'),
            stake_amount=Sum('stake'),
            payout_amount=Sum('payout_amount'),
        )
        stake = float(agg.get('stake_amount') or 0)
        payout = float(agg.get('payout_amount') or 0)
        return {
            'bets_count': int(agg.get('bets_count') or 0),
            'stake_amount': stake,
            'payout_amount': payout,
            'profit': stake - payout,
        }

    gund_period_qs = _scope_bet(Bet.objects.filter(created_at__gte=period_start_utc))

    cq_today = _scope_cricket_cf(CricketBet.objects.filter(created_at__gte=today_start_utc, created_at__lt=today_end_utc))
    cq_yday = _scope_cricket_cf(CricketBet.objects.filter(created_at__gte=yday_start_utc, created_at__lt=yday_end_utc))
    cq_period = _scope_cricket_cf(CricketBet.objects.filter(created_at__gte=period_start_utc))

    cf_today = _scope_cricket_cf(CockFightBet.objects.filter(created_at__gte=today_start_utc, created_at__lt=today_end_utc))
    cf_yday = _scope_cricket_cf(CockFightBet.objects.filter(created_at__gte=yday_start_utc, created_at__lt=yday_end_utc))
    cf_period = _scope_cricket_cf(CockFightBet.objects.filter(created_at__gte=period_start_utc))

    cricket_today_agg = cq_today.aggregate(
        bets_count=Count('id'), stake_amount=Sum('stake'), payout_amount=Sum('payout_amount'),
    )
    cricket_yday_agg = cq_yday.aggregate(
        bets_count=Count('id'), stake_amount=Sum('stake'), payout_amount=Sum('payout_amount'),
    )
    cf_today_agg = cf_today.aggregate(
        bets_count=Count('id'), stake_amount=Sum('stake'), payout_amount=Sum('payout_amount'),
    )
    cf_yday_agg = cf_yday.aggregate(
        bets_count=Count('id'), stake_amount=Sum('stake'), payout_amount=Sum('payout_amount'),
    )

    cricket_today_active = cq_today.aggregate(n=Count('user_id', distinct=True))['n'] or 0
    cricket_yday_active = cq_yday.aggregate(n=Count('user_id', distinct=True))['n'] or 0
    cf_today_active = cf_today.aggregate(n=Count('user_id', distinct=True))['n'] or 0
    cf_yday_active = cf_yday.aggregate(n=Count('user_id', distinct=True))['n'] or 0

    games = {
        'gunduata': {
            'label': 'Gunduata (Dice)',
            'period': _bet_metric_block(gund_period_qs),
            'today': {
                'bets_count': int(today_bet_agg.get('bets_count') or 0),
                'stake_amount': float(today_bet_agg.get('bets_amount') or 0),
                'payout_amount': float(today_bet_agg.get('payout_amount') or 0),
                'profit': float((today_bet_agg.get('bets_amount') or 0) - (today_bet_agg.get('payout_amount') or 0)),
                'active_bettors': int(today_active_bettors),
            },
            'yesterday': {
                'bets_count': int(yday_bet_agg.get('bets_count') or 0),
                'stake_amount': float(yday_bet_agg.get('bets_amount') or 0),
                'payout_amount': float(yday_bet_agg.get('payout_amount') or 0),
                'profit': float((yday_bet_agg.get('bets_amount') or 0) - (yday_bet_agg.get('payout_amount') or 0)),
                'active_bettors': int(yday_active_bettors),
            },
        },
        'cricket': {
            'label': 'Cricket',
            'period': _cricket_cf_metric_block(cq_period),
            'today': {
                'bets_count': int(cricket_today_agg.get('bets_count') or 0),
                'stake_amount': float(cricket_today_agg.get('stake_amount') or 0),
                'payout_amount': float(cricket_today_agg.get('payout_amount') or 0),
                'profit': float((cricket_today_agg.get('stake_amount') or 0) - (cricket_today_agg.get('payout_amount') or 0)),
                'active_bettors': int(cricket_today_active),
            },
            'yesterday': {
                'bets_count': int(cricket_yday_agg.get('bets_count') or 0),
                'stake_amount': float(cricket_yday_agg.get('stake_amount') or 0),
                'payout_amount': float(cricket_yday_agg.get('payout_amount') or 0),
                'profit': float((cricket_yday_agg.get('stake_amount') or 0) - (cricket_yday_agg.get('payout_amount') or 0)),
                'active_bettors': int(cricket_yday_active),
            },
        },
        'cockfight': {
            'label': 'Cock fight',
            'period': _cricket_cf_metric_block(cf_period),
            'today': {
                'bets_count': int(cf_today_agg.get('bets_count') or 0),
                'stake_amount': float(cf_today_agg.get('stake_amount') or 0),
                'payout_amount': float(cf_today_agg.get('payout_amount') or 0),
                'profit': float((cf_today_agg.get('stake_amount') or 0) - (cf_today_agg.get('payout_amount') or 0)),
                'active_bettors': int(cf_today_active),
            },
            'yesterday': {
                'bets_count': int(cf_yday_agg.get('bets_count') or 0),
                'stake_amount': float(cf_yday_agg.get('stake_amount') or 0),
                'payout_amount': float(cf_yday_agg.get('payout_amount') or 0),
                'profit': float((cf_yday_agg.get('stake_amount') or 0) - (cf_yday_agg.get('payout_amount') or 0)),
                'active_bettors': int(cf_yday_active),
            },
        },
    }

    current_round_total_amount = 0
    current_round_total_bets = 0
    bets_by_number_list = []
    current_round_bettor_ids = set()
    current_round_active_bettors = 0
    if current_round:
        current_round_bets = _scope_bet(Bet.objects.filter(round=current_round))
        current_round_total_bets = current_round_bets.count()
        current_round_total_amount = current_round_bets.aggregate(Sum('chip_amount'))['chip_amount__sum'] or 0
        current_round_bettor_ids = set(
            str(uid) for uid in current_round_bets.values_list('user_id', flat=True).distinct()
        )
        # "Actively playing" = distinct users with at least one bet in this round (scoped for franchise).
        # Do not union Redis game_watching_users: it includes spectators, other franchises, and stale WS
        # entries after disconnect, which made the dashboard count wrong.
        current_round_active_bettors = len(current_round_bettor_ids)
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

    # Prepare response data (JSON-serializable)
    data = {
        'timer': timer,
        'status': status,
        'round_id': current_round.round_id if current_round else None,
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
        'current_round_active_bettors': current_round_active_bettors,
        'bets_by_number_list': bets_by_number_list,
        'total_bets': total_bets_count,
        'total_amount': float(overall_total_amount),
        'total_payout': float(overall_total_payout),
        'total_profit': float(overall_total_profit),
        'daily': {
            'timezone': 'IST',
            'today': {
                'date': str(today_ist_date),
                'deposits_count': int(today_deposit_agg.get('count') or 0),
                'deposits_amount': float(today_deposit_agg.get('amount') or 0),
                'withdraws_count': int(today_withdraw_agg.get('count') or 0),
                'withdraws_amount': float(today_withdraw_agg.get('amount') or 0),
                'bets_count': int(today_bet_agg.get('bets_count') or 0),
                'bets_amount': float(today_bet_agg.get('bets_amount') or 0),
                'payout_amount': float(today_bet_agg.get('payout_amount') or 0),
                'profit': float((today_bet_agg.get('bets_amount') or 0) - (today_bet_agg.get('payout_amount') or 0)),
                'active_bettors': int(today_active_bettors or 0),
                'new_users': int(today_new_users or 0),
            },
            'yesterday': {
                'date': str(yday_ist_date),
                'deposits_count': int(yday_deposit_agg.get('count') or 0),
                'deposits_amount': float(yday_deposit_agg.get('amount') or 0),
                'withdraws_count': int(yday_withdraw_agg.get('count') or 0),
                'withdraws_amount': float(yday_withdraw_agg.get('amount') or 0),
                'bets_count': int(yday_bet_agg.get('bets_count') or 0),
                'bets_amount': float(yday_bet_agg.get('bets_amount') or 0),
                'payout_amount': float(yday_bet_agg.get('payout_amount') or 0),
                'profit': float((yday_bet_agg.get('bets_amount') or 0) - (yday_bet_agg.get('payout_amount') or 0)),
                'active_bettors': int(yday_active_bettors or 0),
                'new_users': int(yday_new_users or 0),
            },
        },
        'games': games,
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
                            
                            # 2. Update manual_dice_result for the engine to pick up (see game_engine_v3 run_game_loop)
                            # Format: "1,2,3,4,5,6" — when present at result time, engine skips smart/random dice.
                            if len(dice_values_list) == 6 and all(1 <= d <= 6 for d in dice_values_list):
                                manual_dice_str = ",".join(str(d) for d in dice_values_list)
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
    
    # Fix stale rounds so we don't show old rounds stuck as "Betting"
    try:
        from datetime import timedelta
        now = timezone.now()
        # 1) Rounds that have result data but are still BETTING -> RESULT
        GameRound.objects.filter(
            status='BETTING'
        ).filter(
            Q(dice_result__isnull=False) & ~Q(dice_result='') | Q(result_time__isnull=False)
        ).update(status='RESULT')
        # 2) Any BETTING or CLOSED round that has exceeded its round duration -> RESULT
        # (round_result event may never have been processed; use each round's round_end_seconds)
        for round_obj in GameRound.objects.filter(status__in=['BETTING', 'CLOSED']).only('id', 'start_time', 'round_end_seconds'):
            try:
                duration_sec = (round_obj.round_end_seconds or 90) + 60  # round length + 60s buffer
                if (now - round_obj.start_time).total_seconds() > duration_sec:
                    GameRound.objects.filter(pk=round_obj.pk).update(status='RESULT')
            except Exception:
                pass
        # 3) Fallback: any BETTING/CLOSED round older than 5 minutes -> RESULT
        cutoff = now - timedelta(seconds=300)
        GameRound.objects.filter(status__in=['BETTING', 'CLOSED'], start_time__lt=cutoff).update(status='RESULT')
    except Exception:
        pass

    # Get search query and filters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    controlled_only = request.GET.get('controlled_only') == '1'
    date_range = request.GET.get('date_range', '').strip()  # '', 'last_7_days', 'last_30_days', 'last_month'

    # Date range filter for round start_time
    from datetime import timedelta, date
    today = timezone.now().date()
    date_from = date_to = None
    if date_range == 'last_7_days':
        date_from = today - timedelta(days=7)
        date_to = today
    elif date_range == 'last_30_days':
        date_from = today - timedelta(days=30)
        date_to = today
    elif date_range == 'last_month':
        # Previous calendar month
        first_this_month = today.replace(day=1)
        last_last_month = first_this_month - timedelta(days=1)
        date_from = last_last_month.replace(day=1)
        date_to = last_last_month

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

    # Apply date range filter
    if date_from is not None:
        recent_rounds_list = recent_rounds_list.filter(start_time__date__gte=date_from)
    if date_to is not None:
        recent_rounds_list = recent_rounds_list.filter(start_time__date__lte=date_to)

    # Paginate so older history is accessible (page 2, 3, ...)
    recent_rounds_list = recent_rounds_list.order_by('-start_time')
    paginator = Paginator(recent_rounds_list, 50)
    page_number = request.GET.get('page', 1)
    try:
        page_number = max(1, min(int(page_number), 999))
    except (ValueError, TypeError):
        page_number = 1
    page_obj = paginator.get_page(page_number)
    recent_rounds_list = list(page_obj.object_list)
    
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
        'page_obj': page_obj,
        'controlled_round_ids': controlled_round_ids_set,
        'controlled_only': controlled_only,
        'recent_bets': recent_bets,
        'dice_control_history': dice_control_history,
        'total_rounds': total_rounds,
        'total_bets_count': total_bets_count,
        'total_bets_amount': total_bets_amount,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_range': date_range,
        'date_from': date_from,
        'date_to': date_to,
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

        if action == 'deposit' and deposit_payment_reference_in_use(utr_number):
            messages.error(
                request,
                'This UTR is already used by another pending or approved deposit. Each UTR must be unique.',
            )
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
                
                # 1️⃣ Update DB atomically (balance + total_deposits for withdrawable rule)
                Wallet.objects.filter(pk=wallet.pk).update(
                    balance=F('balance') + amount_decimal,
                    total_deposits=F('total_deposits') + int(amount_decimal),
                )
                wallet.refresh_from_db()
                Wallet.apply_deposit_rotation_credit(wallet.pk, int(amount_decimal))
                
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
        # Wallet formula: unavailable = max(0, total_deposits - turnover), withdrawable = balance - unavailable
        'wallet_unavailable': wallet.computed_unavailable_balance,
        'wallet_withdrawable': wallet.withdrawable_balance,
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

    effective_admin = get_effective_admin(request.user)
    # Get all bets
    all_bets_list = Bet.objects.select_related('user', 'round').all().order_by('-created_at')
    if not is_super_admin(effective_admin):
        all_bets_list = all_bets_list.filter(user__worker=effective_admin)

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

    is_franchise_scope = not is_super_admin(effective_admin)
    context = get_admin_context(request, {
        'all_bets': all_bets_list,
        'total_bets_count': total_bets_count,
        'total_bets_amount': total_bets_amount,
        'total_payouts': total_payouts,
        'total_winners': total_winners,
        'search_query': search_query,
        'status_filter': status_filter,
        'page': 'all-bets',
        'is_franchise_scope': is_franchise_scope,
        'scope_label': 'Your franchise' if is_franchise_scope else None,
    })

    return render(request, 'admin/all_bets.html', context)

@admin_required
def wallets(request):
    """Wallets page with filters and pagination"""
    if not has_menu_permission(request.user, 'wallets'):
        messages.error(request, 'You do not have permission to view wallets.')
        return redirect('admin_dashboard')

    effective_admin = get_effective_admin(request.user)
    base_wallets = Wallet.objects.select_related('user').all()
    if not is_super_admin(effective_admin):
        base_wallets = base_wallets.filter(user__worker=effective_admin)
        
    # Get filter parameters
    balance_filter = request.GET.get('balance', 'all')  # all, has_balance, zero
    search_query = request.GET.get('search', '').strip()
    sort_by = request.GET.get('sort', 'balance_desc')  # balance_desc, balance_asc, username_asc, username_desc
    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1
    
    wallets_query = base_wallets
    
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
    
    # Calculate stats from same base (franchise-scoped)
    total_wallets = base_wallets.count()
    total_balance = base_wallets.aggregate(Sum('balance'))['balance__sum'] or 0
    active_wallets = base_wallets.filter(balance__gt=0).count()
    zero_balance_wallets = base_wallets.filter(balance=0).count()
    
    # Pagination - 50 wallets per page for better performance
    paginator = Paginator(wallets_query, 50)
    try:
        page_obj = paginator.get_page(page_number)
    except Exception:
        page_obj = None
    
    is_franchise_scope = not is_super_admin(effective_admin)
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
        'is_franchise_scope': is_franchise_scope,
        'scope_label': 'Your franchise' if is_franchise_scope else None,
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
    
    # Effective admin: workers see their assigned admin's queue; others see their own
    effective_admin = get_effective_admin(request.user)
    # Base queryset for deposit requests
    deposit_requests_qs = DepositRequest.objects.select_related('user', 'processed_by').all()
    # Super Admin sees ALL requests (same data as user detail /tab=deposits). Approve still blocks franchise players for super.
    # Franchise admins see only their queue.
    if not is_super_admin(effective_admin):
        deposit_requests_qs = deposit_requests_qs.filter(user__worker=effective_admin)
    
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
    
    stats_base = DepositRequest.objects.all()
    if not is_super_admin(effective_admin):
        stats_base = stats_base.filter(user__worker=effective_admin)
    total_requests = stats_base.count()
    pending_requests = stats_base.filter(status='PENDING').count()
    approved_requests = stats_base.filter(status='APPROVED').count()
    rejected_requests = stats_base.filter(status='REJECTED').count()
    total_amount = stats_base.filter(status='APPROVED').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_amount = stats_base.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Latest request ID for polling
    latest_request_id = stats_base.order_by('-id').first()
    latest_id = latest_request_id.id if latest_request_id else 0
    
    my_franchise_balance = None
    my_franchise_balance_display = ''
    my_franchise_name = ''
    balance_is_low = False
    LOW_BALANCE_THRESHOLD = 1000
    if not is_super_admin(effective_admin):
        try:
            fb = FranchiseBalance.objects.get(user=effective_admin)
            my_franchise_balance = fb.balance
            my_franchise_name = fb.franchise_name or ''
            balance_is_low = my_franchise_balance < LOW_BALANCE_THRESHOLD
        except FranchiseBalance.DoesNotExist:
            my_franchise_balance = 0
            balance_is_low = True
        from .utils import format_indian_int
        my_franchise_balance_display = format_indian_int(my_franchise_balance)
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
        'my_franchise_balance': my_franchise_balance,
        'my_franchise_balance_display': my_franchise_balance_display,
        'my_franchise_name': my_franchise_name,
        'balance_is_low': balance_is_low,
    })
    
    return render(request, 'admin/deposit_requests.html', context)


@admin_required
def check_new_deposit_requests(request):
    """API endpoint to check for new deposit requests"""
    last_id = int(request.GET.get('last_id', 0))
    
    effective_admin = get_effective_admin(request.user)
    new_requests = DepositRequest.objects.filter(id__gt=last_id, status='PENDING')
    if not is_super_admin(effective_admin):
        new_requests = new_requests.filter(user__worker=effective_admin)
        
    new_requests = new_requests.select_related('user').order_by('-id')[:10]
    
    requests_data = []
    for req in new_requests:
        requests_data.append({
            'id': req.id,
            'user': req.user.username,
            'amount': float(req.amount),
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    
    pending_qs = DepositRequest.objects.filter(status='PENDING')
    if not is_super_admin(effective_admin):
        pending_qs = pending_qs.filter(user__worker=effective_admin)
    return JsonResponse({
        'new_requests': requests_data,
        'latest_id': DepositRequest.objects.order_by('-id').first().id if DepositRequest.objects.exists() else last_id,
        'pending_count': pending_qs.count(),
    })

@admin_required
def approve_deposit(request, pk):
    """Approve a deposit request"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method. Please use the approve button.')
        return redirect('deposit_requests')
    
    try:
        deposit = DepositRequest.objects.select_related('user').get(pk=pk)
        effective_admin = get_effective_admin(request.user)
        # Super Admin may approve any deposit (franchise balance is not deducted for superuser).
        if not is_super_admin(effective_admin) and getattr(deposit.user, 'worker_id', None) != effective_admin.id:
            messages.error(request, 'You can only approve deposit requests for users under your admin.')
            return redirect('deposit_requests')
        with db_transaction.atomic():
            deposit = DepositRequest.objects.select_for_update().get(pk=pk)
            if deposit.status != 'PENDING':
                messages.error(request, 'Deposit request has already been processed.')
                return redirect('deposit_requests')

            utr = request.POST.get('utr', '').strip()
            if not utr:
                messages.error(request, 'UTR number is compulsory for approving deposits.')
                return redirect('deposit_requests')
            if deposit_payment_reference_in_use(utr, exclude_pk=deposit.pk):
                messages.error(
                    request,
                    'This UTR is already used by another pending or approved deposit. Each UTR must be unique.',
                )
                return redirect('deposit_requests')
            
            # Calculate final amount with USDT bonus if applicable
            final_amount = deposit.amount
            bonus_amount = Decimal('0.00')
            if deposit.payment_method and deposit.payment_method.method_type in ['USDT_TRC20', 'USDT_BEP20']:
                bonus_amount = deposit.amount * Decimal('0.05')
                final_amount += bonus_amount
            final_amount_int = int(final_amount)
            
            # Franchise balance: deduct from processing admin's balance (skip for superuser)
            if not is_super_admin(request.user):
                fb, _ = FranchiseBalance.objects.get_or_create(user=request.user, defaults={'balance': 0})
                fb = FranchiseBalance.objects.select_for_update().get(pk=fb.pk)
                if fb.balance < final_amount_int:
                    messages.error(request, f'Insufficient franchise balance. Your balance: ₹{fb.balance}, required: ₹{final_amount_int}. Contact super admin for top-up.')
                    return redirect('deposit_requests')
                FranchiseBalance.objects.filter(pk=fb.pk).update(balance=F('balance') - final_amount_int)
            
            wallet, _ = Wallet.objects.get_or_create(user=deposit.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            balance_before = wallet.balance
            
            # 1️⃣ Update DB atomically (balance + total_deposits for withdrawable rule)
            Wallet.objects.filter(pk=wallet.pk).update(
                balance=F('balance') + final_amount,
                total_deposits=F('total_deposits') + int(final_amount),
            )
            wallet.refresh_from_db()
            Wallet.apply_deposit_rotation_credit(wallet.pk, int(final_amount))
            
            deposit.status = 'APPROVED'
            deposit.processed_by = request.user
            deposit.processed_at = timezone.now()
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
                    # Referral bonus needs to be rotated 1 time (counts as deposit for withdrawable rule)
                    ref_wallet.add(referral_bonus, is_bonus=True)
                    Wallet.objects.filter(pk=ref_wallet.pk).update(total_deposits=F('total_deposits') + int(referral_bonus))
                    ref_wallet.refresh_from_db()
                    Wallet.apply_deposit_rotation_credit(ref_wallet.pk, int(referral_bonus))

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
            deposit = DepositRequest.objects.select_related('user').get(pk=pk)
            effective_admin = get_effective_admin(request.user)
            if not is_super_admin(effective_admin) and getattr(deposit.user, 'worker_id', None) != effective_admin.id:
                messages.error(request, 'You can only reject deposit requests for users under your admin.')
                return redirect('deposit_requests')
            with db_transaction.atomic():
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
        deposit = DepositRequest.objects.select_related('user').get(pk=pk)
        effective_admin = get_effective_admin(request.user)
        if not is_super_admin(effective_admin) and getattr(deposit.user, 'worker_id', None) != effective_admin.id:
            messages.error(request, 'You can only edit deposit requests for users under your admin.')
            return redirect('deposit_requests')
        with db_transaction.atomic():
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

    effective_admin = get_effective_admin(request.user)
    withdraw_requests_list = WithdrawRequest.objects.select_related('user', 'processed_by').all()
    if is_super_admin(effective_admin):
        withdraw_requests_list = withdraw_requests_list.filter(user__worker__isnull=True)
    else:
        withdraw_requests_list = withdraw_requests_list.filter(user__worker=effective_admin)
    
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

    stats_base = WithdrawRequest.objects.all()
    if is_super_admin(effective_admin):
        stats_base = stats_base.filter(user__worker__isnull=True)
    else:
        stats_base = stats_base.filter(user__worker=effective_admin)
    total_requests = stats_base.count()
    pending_requests = stats_base.filter(status='PENDING').count()
    approved_requests = stats_base.filter(status='APPROVED').count()
    rejected_requests = stats_base.filter(status='REJECTED').count()
    total_amount = stats_base.filter(status='APPROVED').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_amount = stats_base.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Get the latest request ID for polling
    latest_request_id = stats_base.order_by('-id').first()
    latest_id = latest_request_id.id if latest_request_id else 0
    
    my_franchise_balance = None
    my_franchise_balance_display = ''
    if not is_super_admin(effective_admin):
        try:
            fb = FranchiseBalance.objects.get(user=effective_admin)
            my_franchise_balance = fb.balance
        except FranchiseBalance.DoesNotExist:
            my_franchise_balance = 0
        from .utils import format_indian_int
        my_franchise_balance_display = format_indian_int(my_franchise_balance)
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
        'my_franchise_balance': my_franchise_balance,
        'my_franchise_balance_display': my_franchise_balance_display,
    })

    return render(request, 'admin/withdraw_requests.html', context)


@admin_required
def check_new_withdraw_requests(request):
    """API endpoint to check for new withdraw requests"""
    last_id = int(request.GET.get('last_id', 0))
    effective_admin = get_effective_admin(request.user)
    new_requests = WithdrawRequest.objects.filter(id__gt=last_id, status='PENDING')
    if is_super_admin(effective_admin):
        new_requests = new_requests.filter(user__worker__isnull=True)
    else:
        new_requests = new_requests.filter(user__worker=effective_admin)
    new_requests = new_requests.select_related('user').order_by('-id')[:10]
    
    requests_data = []
    for req in new_requests:
        requests_data.append({
            'id': req.id,
            'user': req.user.username,
            'amount': float(req.amount),
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
    
    pending_qs = WithdrawRequest.objects.filter(status='PENDING')
    if is_super_admin(effective_admin):
        pending_qs = pending_qs.filter(user__worker__isnull=True)
    else:
        pending_qs = pending_qs.filter(user__worker=effective_admin)
    return JsonResponse({
        'new_requests': requests_data,
        'latest_id': WithdrawRequest.objects.order_by('-id').first().id if WithdrawRequest.objects.exists() else last_id,
        'pending_count': pending_qs.count(),
    })

@admin_required
def approve_withdraw(request, pk):
    """Approve a withdraw request - Deducts money from wallet and sets status to COMPLETED immediately"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method. Please use the approve button.')
        return redirect('withdraw_requests')
    
    try:
        withdraw = WithdrawRequest.objects.select_related('user').get(pk=pk)
        effective_admin = get_effective_admin(request.user)
        if is_super_admin(effective_admin):
            if getattr(withdraw.user, 'worker_id', None) is not None:
                messages.error(request, 'Super Admin can only approve withdraw requests from players not under a franchise.')
                return redirect('withdraw_requests')
        elif getattr(withdraw.user, 'worker_id', None) != effective_admin.id:
            messages.error(request, 'You can only approve withdraw requests for users under your admin.')
            return redirect('withdraw_requests')
        with db_transaction.atomic():
            withdraw = WithdrawRequest.objects.select_for_update().get(pk=pk)
            if withdraw.status != 'PENDING':
                messages.error(request, 'Withdraw request has already been processed.')
                return redirect('withdraw_requests')
            
            wallet, _ = Wallet.objects.get_or_create(user=withdraw.user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)

            # Money is already deducted from Redis and DB when the user created the withdraw request
            # (initiate_withdraw). So we do NOT check wallet.balance here — it would fail because
            # balance was already reduced (e.g. user had 2500, requested 2500, balance is now 0).

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

            # Snapshot wallet; reset deposit rotation (new cycle after completed withdrawal)
            Wallet.objects.filter(pk=wallet.pk).update(
                total_deposits_at_last_withdraw=wallet.total_deposits,
                turnover_at_last_withdraw=wallet.turnover,
                deposit_rotation_lock=0,
                deposit_rotation_baseline_turnover=wallet.turnover,
            )

            # Franchise balance: add withdrawal amount to processing admin's balance (skip for superuser)
            if not is_super_admin(request.user):
                fb, _ = FranchiseBalance.objects.get_or_create(user=request.user, defaults={'balance': 0})
                FranchiseBalance.objects.filter(pk=fb.pk).update(balance=F('balance') + withdraw.amount)

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
        withdraw = WithdrawRequest.objects.select_related('user').get(pk=pk)
        effective_admin = get_effective_admin(request.user)
        if is_super_admin(effective_admin):
            if getattr(withdraw.user, 'worker_id', None) is not None:
                messages.error(request, 'Super Admin can only complete payments for withdraw requests from players not under a franchise.')
                return redirect('withdraw_requests')
        elif getattr(withdraw.user, 'worker_id', None) != effective_admin.id:
            messages.error(request, 'You can only complete payments for withdraw requests from users under your admin.')
            return redirect('withdraw_requests')
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
            withdraw = WithdrawRequest.objects.select_related('user').get(pk=pk)
            effective_admin = get_effective_admin(request.user)
            if is_super_admin(effective_admin):
                if getattr(withdraw.user, 'worker_id', None) is not None:
                    messages.error(request, 'Super Admin can only reject withdraw requests from players not under a franchise.')
                    return redirect('withdraw_requests')
            elif getattr(withdraw.user, 'worker_id', None) != effective_admin.id:
                messages.error(request, 'You can only reject withdraw requests for users under your admin.')
                return redirect('withdraw_requests')
            with db_transaction.atomic():
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
    """Reports page showing financial summary. Franchise owners see only transactions of players under their franchise."""
    if not has_menu_permission(request.user, 'transactions'):
        messages.error(request, 'You do not have permission to view reports.')
        return redirect('admin_dashboard')

    from datetime import timedelta
    from django.db.models.functions import TruncDate

    effective_admin = get_effective_admin(request.user)
    transactions_query = Transaction.objects.all()
    if not is_super_admin(effective_admin):
        transactions_query = transactions_query.filter(user__worker=effective_admin)

    # Get filters: search and optional date range. Default = last 7 days when no params; overall=1 = all time.
    search_query = request.GET.get('search', '').strip()
    from_date_str = request.GET.get('from_date', '').strip()
    to_date_str = request.GET.get('to_date', '').strip()
    show_overall = request.GET.get('overall', '').strip().lower() in ('1', 'true', 'yes')

    today = timezone.now().date()
    from_date = None
    to_date = None

    if from_date_str:
        try:
            from_date = _dt.datetime.strptime(from_date_str, '%Y-%m-%d').date()
        except ValueError:
            from_date = None
    if to_date_str:
        try:
            to_date = _dt.datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            to_date = None

    # Default: when no date params and not "overall", use last 7 days
    if not show_overall and from_date is None and to_date is None:
        from_date = today - timedelta(days=6)  # 7 days inclusive
        to_date = today
        from_date_str = from_date.strftime('%Y-%m-%d')
        to_date_str = to_date.strftime('%Y-%m-%d')

    if from_date is not None:
        transactions_query = transactions_query.filter(created_at__date__gte=from_date)
    if to_date is not None:
        transactions_query = transactions_query.filter(created_at__date__lte=to_date)

    date_filter_applied = from_date is not None or to_date is not None

    # Apply search filter (filter by user)
    if search_query:
        transactions_query = transactions_query.filter(
            Q(user__username__icontains=search_query) |
            Q(user__phone_number__icontains=search_query)
        )

    # Calculate stats from (possibly filtered) queryset
    total_transactions = transactions_query.count()
    total_deposits = transactions_query.filter(transaction_type='DEPOSIT').aggregate(Sum('amount'))['amount__sum'] or 0
    total_withdraws = transactions_query.filter(transaction_type='WITHDRAW').aggregate(Sum('amount'))['amount__sum'] or 0
    total_bets = transactions_query.filter(transaction_type='BET').aggregate(Sum('amount'))['amount__sum'] or 0
    total_wins = transactions_query.filter(transaction_type='WIN').aggregate(Sum('amount'))['amount__sum'] or 0
    admin_profit = total_bets - total_wins

    # Chart: when custom date range, use that range (up to 90 days for chart); otherwise last 30 days
    if date_filter_applied and from_date is not None and to_date is not None:
        chart_start = from_date
        chart_end = to_date
        if (chart_end - chart_start).days > 90:
            chart_end = chart_start + timedelta(days=90)
    else:
        chart_end = timezone.now().date()
        chart_start = chart_end - timedelta(days=29)

    daily_stats = transactions_query.filter(
        created_at__date__gte=chart_start,
        created_at__date__lte=chart_end,
        transaction_type__in=['BET', 'WIN']
    ).annotate(
        date=TruncDate('created_at')
    ).values('date', 'transaction_type').annotate(
        daily_amount=Sum('amount')
    ).order_by('date')

    profit_data_map = {}
    d = chart_start
    while d <= chart_end:
        profit_data_map[d] = 0
        d += timedelta(days=1)

    for stat in daily_stats:
        date = stat['date']
        amount = stat['daily_amount']
        if stat['transaction_type'] == 'BET':
            profit_data_map[date] += amount
        else:
            profit_data_map[date] -= amount

    chart_labels = [date.strftime('%b %d') for date in sorted(profit_data_map.keys())]
    chart_data = [float(profit_data_map[date]) for date in sorted(profit_data_map.keys())]

    is_franchise_scope = not is_super_admin(effective_admin)
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
        'from_date': from_date_str,
        'to_date': to_date_str,
        'date_filter_applied': date_filter_applied,
        'page': 'transactions',
        'is_franchise_scope': is_franchise_scope,
        'scope_label': 'Your franchise' if is_franchise_scope else None,
    })

    return render(request, 'admin/transactions.html', context)

def _can_access_worker_management(user):
    """Super Admin, or has can_view_admin_management, or is a franchise owner (they manage their own workers)."""
    if is_super_admin(user):
        return True
    if has_menu_permission(user, 'admin_management'):
        return True
    if getattr(user, 'is_franchise_only', False):
        return True
    # Only treat as franchise owner if not assigned under someone else.
    if FranchiseBalance.objects.filter(user=user).exists() and not getattr(user, 'works_under_id', None):
        return True
    return False


@admin_required
def admin_management(request):
    """Worker management: Super Admin sees all workers; franchise owners see only workers under them."""
    if not _can_access_worker_management(request.user):
        messages.error(request, 'You do not have permission to access Worker Management.')
        return redirect('admin_dashboard')
    
    status_filter = request.GET.get('status', 'all')
    is_franchise_scope = not is_super_admin(request.user)
    # Super Admin: all workers (exclude franchise-only). Franchise owner: only workers who work under them.
    if is_super_admin(request.user):
        base_workers = User.objects.filter(is_staff=True, is_franchise_only=False)
    else:
        base_workers = User.objects.filter(is_staff=True, works_under=request.user)
    admin_users = base_workers.order_by('-date_joined')
    if status_filter == 'active':
        admin_users = admin_users.filter(is_active=True)
    elif status_filter == 'inactive':
        admin_users = admin_users.filter(is_active=False)
    
    total_admins = base_workers.count()
    active_admins = base_workers.filter(is_active=True).count()
    inactive_admins = base_workers.filter(is_active=False).count()
    
    admin_list = []
    for user in admin_users:
        try:
            perms = AdminPermissions.objects.get(user=user)
        except AdminPermissions.DoesNotExist:
            perms = AdminPermissions.objects.create(user=user)
        admin_list.append({
            'user': user,
            'permissions': perms,
            'is_superuser': user.is_superuser,
        })
    
    scope_label = 'Your workers' if is_franchise_scope else ''
    context = get_admin_context(request, {
        'admin_list': admin_list,
        'page': 'admin-management',
        'status_filter': status_filter,
        'total_admins': total_admins,
        'active_admins': active_admins,
        'inactive_admins': inactive_admins,
        'is_franchise_scope': is_franchise_scope,
        'scope_label': scope_label,
    })
    return render(request, 'admin/admin_management.html', context)


@admin_required
@require_POST
def toggle_admin_status(request, admin_id):
    """Activate or deactivate a worker. Franchise owners can only toggle workers under them."""
    if not _can_access_worker_management(request.user):
        messages.error(request, 'You do not have permission to access Worker Management.')
        return redirect('admin_dashboard')
    try:
        user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Worker not found.')
        return redirect('admin_management')
    if not is_super_admin(request.user) and getattr(user, 'works_under_id', None) != request.user.id:
        messages.error(request, 'You can only activate/deactivate workers assigned to you.')
        return redirect('admin_management')
    if user.id == request.user.id:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('admin_management')
    if user.is_superuser and User.objects.filter(is_staff=True, is_superuser=True, is_active=True).count() <= 1:
        messages.error(request, 'Cannot deactivate the last active Super Admin.')
        return redirect('admin_management')
    user.is_active = not user.is_active
    user.save()
    status = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f'Worker "{user.username}" has been {status}.')
    next_status = request.POST.get('status') or request.GET.get('status', 'all')
    return redirect('admin_management' + ('?status=' + next_status if next_status != 'all' else ''))


@super_admin_required
def franchise_balance(request):
    """Franchise balance management - Super Admin only. List admins and allocate/top-up balance."""
    if not is_super_admin(request.user):
        messages.error(request, 'Only Super Admins can manage Franchise Balance.')
        return redirect('admin_dashboard')
    
    # POST: add/set balance or save franchise name
    if request.method == 'POST':
        admin_id = request.POST.get('admin_id')
        action = request.POST.get('action', 'add')  # 'add', 'set', or 'save_name'
        try:
            admin_user = User.objects.get(pk=admin_id, is_staff=True)
        except User.DoesNotExist:
            messages.error(request, 'Worker not found.')
            return redirect('franchise_balance')
        if action == 'save_name':
            franchise_name = request.POST.get('franchise_name', '').strip()[:120]
            with db_transaction.atomic():
                fb, _ = FranchiseBalance.objects.get_or_create(user=admin_user, defaults={'balance': 0})
                fb.franchise_name = franchise_name
                fb.save()
            messages.success(request, f"Franchise name for {admin_user.username} set to '{franchise_name or '(empty)'}'.")
            return redirect('franchise_balance')
        if action == 'deactivate_franchise_admin':
            if admin_user.id == request.user.id:
                messages.error(request, 'You cannot deactivate your own account.')
                return redirect('franchise_balance')
            if admin_user.is_superuser:
                messages.error(request, 'Super Admin accounts cannot be deactivated from here.')
                return redirect('franchise_balance')
            with db_transaction.atomic():
                player_count = User.objects.filter(worker=admin_user, is_staff=False).count()
                User.objects.filter(worker=admin_user, is_staff=False).update(worker=request.user)
                admin_user.is_active = False
                admin_user.save()
            messages.success(request, f'"{admin_user.username}" deactivated. {player_count} player(s) reassigned to you (Super Admin).')
            return redirect('franchise_balance')
        if action == 'activate_franchise_admin':
            if admin_user.is_superuser:
                messages.error(request, 'Super Admin is always active.')
                return redirect('franchise_balance')
            admin_user.is_active = True
            admin_user.save()
            messages.success(request, f'"{admin_user.username}" activated.')
            return redirect('franchise_balance')
        if action in ('add', 'set') and not admin_user.is_active:
            messages.error(request, f'Cannot add or set balance for inactive franchise "{admin_user.username}". Activate them first from their details page.')
            return redirect('franchise_balance')
        amount_str = request.POST.get('amount', '').strip()
        try:
            amount = int(amount_str)
            if amount < 0:
                raise ValueError('Amount must be non-negative')
        except (ValueError, TypeError):
            messages.error(request, 'Enter a valid amount (whole number).')
            return redirect('franchise_balance')
        with db_transaction.atomic():
            fb, _ = FranchiseBalance.objects.get_or_create(user=admin_user, defaults={'balance': 0})
            if action == 'set':
                fb.balance = amount
                fb.save()
                balance_after = amount
                FranchiseBalanceLog.objects.create(
                    user=admin_user,
                    action=FranchiseBalanceLog.ACTION_SET,
                    amount=amount,
                    balance_after=balance_after,
                    performed_by=request.user,
                )
            else:
                balance_before = fb.balance
                FranchiseBalance.objects.filter(pk=fb.pk).update(balance=F('balance') + amount)
                FranchiseBalanceLog.objects.create(
                    user=admin_user,
                    action=FranchiseBalanceLog.ACTION_ADD,
                    amount=amount,
                    balance_after=balance_before + amount,
                    performed_by=request.user,
                )
        if action == 'set':
            messages.success(request, f"Franchise balance for {admin_user.username} set to ₹{amount:,}.")
        else:
            messages.success(request, f"Added ₹{amount:,} to {admin_user.username}'s franchise balance.")
        return redirect('franchise_balance')
    
    # GET: list franchise owners only (exclude workers assigned under a franchise owner).
    # A franchise owner is:
    # - Super Admin, OR
    # - explicitly marked is_franchise_only, OR
    # - has a FranchiseBalance row AND is not assigned under another admin (works_under is null)
    franchise_owner_ids = list(FranchiseBalance.objects.values_list('user_id', flat=True).distinct())
    admin_users = (
        User.objects.filter(is_staff=True)
        .filter(
            Q(is_superuser=True)
            | Q(is_franchise_only=True)
            | (Q(id__in=franchise_owner_ids) & Q(works_under_id__isnull=True))
        )
        .order_by('-is_active', 'username')
    )
    admin_list = []
    for user in admin_users:
        try:
            fb = FranchiseBalance.objects.get(user=user)
        except FranchiseBalance.DoesNotExist:
            fb = None
        admin_list.append({
            'user': user,
            'balance': fb.balance if fb else 0,
            'franchise_name': fb.franchise_name if fb else '',
            'is_superuser': user.is_superuser,
        })
    
    context = get_admin_context(request, {
        'page': 'franchise-balance',
        'admin_list': admin_list,
    })
    return render(request, 'admin/franchise_balance.html', context)


def _get_queue_owners():
    """List of admins a worker can be assigned to (Super Admins + franchise admins)."""
    owners = []
    for u in User.objects.filter(is_superuser=True, is_staff=True).order_by('username'):
        owners.append({'id': u.id, 'label': f'{u.username} (Super Admin)'})
    franchise_owner_ids = list(FranchiseBalance.objects.values_list('user_id', flat=True).distinct())
    for u in (
        User.objects.filter(is_staff=True, is_superuser=False, works_under_id__isnull=True)
        .filter(Q(is_franchise_only=True) | Q(id__in=franchise_owner_ids))
        .order_by('username')
    ):
        owners.append({'id': u.id, 'label': u.username})
    return owners


def _get_queue_owners_for_request(request):
    """For Super Admin: all queue owners. For franchise owner: only themselves (workers they create work under them)."""
    if is_super_admin(request.user):
        return _get_queue_owners()
    return [{'id': request.user.id, 'label': request.user.username}]


@admin_required
def create_admin(request):
    """Create a new worker. Super Admin can assign to any queue; franchise owner can only create workers under themselves."""
    if not _can_access_worker_management(request.user):
        messages.error(request, 'You do not have permission to access Worker Management.')
        return redirect('admin_dashboard')
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
            'can_view_withdraw_requests': request.POST.get('can_view_withdraw_requests') == 'on',
            'can_view_transactions': request.POST.get('can_view_transactions') == 'on',
            'can_view_game_history': request.POST.get('can_view_game_history', 'on') == 'on',
            'can_view_game_settings': request.POST.get('can_view_game_settings') == 'on',
            'can_view_help_center': request.POST.get('can_view_help_center') == 'on',
            'can_view_white_label': request.POST.get('can_view_white_label') == 'on',
            'can_view_admin_management': request.POST.get('can_view_admin_management') == 'on',
            'can_manage_payment_methods': request.POST.get('can_manage_payment_methods') == 'on',
        }
        
        # Validation
        if not username or not password:
            messages.error(request, 'Username and password are required.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions, 'queue_owners': _get_queue_owners_for_request(request)})
        
        if password != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions, 'queue_owners': _get_queue_owners_for_request(request)})

        if len(password) < 4:
            messages.error(request, 'Password must be at least 4 characters long.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions, 'queue_owners': _get_queue_owners_for_request(request)})
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'admin/create_admin.html', {'permissions': permissions, 'queue_owners': _get_queue_owners_for_request(request)})
        
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
            # Super Admin can assign worker to any queue; franchise owner can only assign to themselves
            if is_super_admin(request.user):
                works_under_id = request.POST.get('works_under_id', '').strip()
                if works_under_id:
                    try:
                        admin_user = User.objects.get(pk=int(works_under_id), is_staff=True)
                        if admin_user.id != user.id:
                            user.works_under = admin_user
                            user.save(update_fields=['works_under_id'])
                    except (ValueError, User.DoesNotExist):
                        pass
            else:
                user.works_under = request.user
                user.save(update_fields=['works_under_id'])
            password_auto_generated = request.POST.get('password_auto_generated', 'false') == 'true'
            if password_auto_generated:
                messages.success(request, f'🎉 Admin user "{username}" created successfully! 🔐 Generated Password: <strong style="font-family: monospace; background: #f0fdf4; padding: 4px 8px; border-radius: 4px; color: #166534;">{password}</strong><br><small style="color: #666;">⚠️ Save this password securely - it will only be shown once!</small>')
            else:
                messages.success(request, f'Admin user "{username}" created successfully!')
            return redirect('admin_management')
        except Exception as e:
            messages.error(request, f'Error creating admin: {str(e)}')
            return render(request, 'admin/create_admin.html', {'permissions': permissions, 'queue_owners': _get_queue_owners_for_request(request)})
    
    return render(request, 'admin/create_admin.html', {'queue_owners': _get_queue_owners_for_request(request)})


@super_admin_required
def franchise_admin_details(request, admin_id):
    """Franchise owner user info only: username, balance, stats, balance history, franchise name. No menu permissions."""
    try:
        user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Franchise admin not found.')
        return redirect('franchise_balance')
    try:
        fb = FranchiseBalance.objects.get(user=user)
        franchise_name = fb.franchise_name or ''
        balance = fb.balance
        package_name = fb.package_name or ''
        help_whatsapp_number = fb.help_whatsapp_number or ''
        help_telegram = fb.help_telegram or ''
    except FranchiseBalance.DoesNotExist:
        franchise_name = ''
        balance = 0
        package_name = ''
        help_whatsapp_number = ''
        help_telegram = ''
    form_username = None
    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        if action == 'change_password':
            if user.is_superuser:
                messages.error(request, 'Super Admin password cannot be changed from this page.')
            else:
                new_password = (request.POST.get('new_password') or '').strip()
                new_password_confirm = (request.POST.get('new_password_confirm') or '').strip()
                if not new_password:
                    messages.error(request, 'New password is required.')
                elif len(new_password) < 4:
                    messages.error(request, 'Password must be at least 4 characters.')
                elif new_password != new_password_confirm:
                    messages.error(request, 'Passwords do not match.')
                else:
                    user.set_password(new_password)
                    user.save()
                    messages.success(request, f'Password updated for "{user.username}".')
            return redirect('franchise_admin_details', admin_id=user.id)
        if action == 'assign_player':
            # Assign an existing player (by phone or username) to this franchise admin
            raw_input = (request.POST.get('assign_phone') or '').strip()
            if not raw_input:
                messages.error(request, 'Please enter a phone number or username.')
            else:
                from accounts.sms_service import sms_service
                player = None
                clean_phone = sms_service._clean_phone_number(raw_input, for_sms=False)
                player = User.objects.filter(
                    Q(phone_number=clean_phone) | Q(phone_number=raw_input)
                ).filter(is_staff=False, is_superuser=False).first()
                if not player:
                    digits = ''.join(c for c in raw_input if c.isdigit())
                    if digits:
                        player = (
                            User.objects.filter(phone_number=digits).filter(is_staff=False, is_superuser=False).first()
                            or User.objects.filter(phone_number__endswith=digits[-10:] if len(digits) >= 10 else digits).filter(is_staff=False, is_superuser=False).first()
                        )
                if not player:
                    player = User.objects.filter(username__iexact=raw_input).filter(is_staff=False, is_superuser=False).first()
                if not player:
                    messages.error(request, f'No player found with phone or username "{raw_input}".')
                elif player.worker_id == user.id:
                    messages.info(request, f'"{player.username}" is already under this franchise.')
                else:
                    old_worker = getattr(player.worker, 'username', None) or 'Super Admin'
                    player.worker = user
                    player.save(update_fields=['worker_id'])
                    messages.success(request, f'"{player.username}" assigned to this franchise. (Was under {old_worker})')
            return redirect('franchise_admin_details', admin_id=user.id)
        if action == 'deactivate_franchise_admin':
            if user.id == request.user.id:
                messages.error(request, 'You cannot deactivate your own account.')
            elif user.is_superuser:
                messages.error(request, 'Super Admin accounts cannot be deactivated from here.')
            else:
                with db_transaction.atomic():
                    player_count = User.objects.filter(worker=user, is_staff=False).count()
                    User.objects.filter(worker=user, is_staff=False).update(worker=request.user)
                    user.is_active = False
                    user.save()
                messages.success(request, f'"{user.username}" deactivated. {player_count} player(s) reassigned to you (Super Admin).')
            return redirect('franchise_admin_details', admin_id=user.id)
        if action == 'activate_franchise_admin':
            if user.is_superuser:
                messages.success(request, 'Super Admin is always active.')
            else:
                user.is_active = True
                user.save()
                messages.success(request, f'"{user.username}" activated.')
            return redirect('franchise_admin_details', admin_id=user.id)
        # save_settings or empty: save username + Help Center (package name, WhatsApp, Telegram)
        new_username = (request.POST.get('username') or '').strip()
        updated = []
        has_error = False
        if new_username != user.username:
            if not new_username:
                messages.error(request, 'Username cannot be empty.')
                has_error = True
            elif User.objects.filter(username=new_username).exclude(pk=user.pk).exists():
                messages.error(request, f'Username "{new_username}" is already taken.')
                has_error = True
            else:
                user.username = new_username
                user.save()
                updated.append('username')
        if has_error:
            form_username = new_username
        else:
            if updated:
                messages.success(request, 'Username updated.')
            # Save Help Center package name only (WhatsApp/Telegram are set by franchise on Help Center page)
            fb, _ = FranchiseBalance.objects.get_or_create(user=user, defaults={'balance': 0})
            pkg = (request.POST.get('package_name') or '').strip()[:255]
            help_saved = False
            duplicate_pkg = False
            if pkg != (fb.package_name or ''):
                if pkg and FranchiseBalance.objects.filter(package_name=pkg).exclude(user=user).exists():
                    messages.error(request, f'Package name "{pkg}" is already used by another franchise.')
                    package_name = pkg
                    duplicate_pkg = True
                else:
                    fb.package_name = pkg or None
                    fb.save()
                    help_saved = True
                    if not updated:
                        messages.success(request, 'Package name saved.')
            if updated or help_saved:
                return redirect('franchise_admin_details', admin_id=user.id)
        # Re-read help fields for display after POST (keep form values when duplicate_pkg error was shown)
        if request.method == 'POST' and not duplicate_pkg:
            try:
                fb = FranchiseBalance.objects.get(user=user)
                package_name = fb.package_name or ''
                help_whatsapp_number = fb.help_whatsapp_number or ''
                help_telegram = fb.help_telegram or ''
            except FranchiseBalance.DoesNotExist:
                package_name = help_whatsapp_number = help_telegram = ''
    clients_count = User.objects.filter(worker=user, is_staff=False).count()
    total_deposits = (
        DepositRequest.objects.filter(user__worker=user, status='APPROVED')
        .aggregate(s=Coalesce(Sum('amount'), 0))['s'] or 0
    )
    total_withdrawals = (
        WithdrawRequest.objects.filter(
            user__worker=user,
            status__in=['APPROVED', 'COMPLETED'],
        ).aggregate(s=Coalesce(Sum('amount'), 0))['s'] or 0
    )
    segment_profit = total_deposits - total_withdrawals
    balance_logs = FranchiseBalanceLog.objects.filter(user=user).select_related('performed_by').order_by('-created_at')[:200]
    context = get_admin_context(request, {
        'admin_user': user,
        'franchise_name': franchise_name,
        'balance': balance,
        'page': 'franchise-balance',
        'clients_count': clients_count,
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'segment_profit': segment_profit,
        'balance_logs': balance_logs,
        'package_name': package_name,
        'help_whatsapp_number': help_whatsapp_number,
        'help_telegram': help_telegram,
    })
    if form_username is not None:
        context['form_username'] = form_username
    return render(request, 'admin/franchise_admin_details.html', context)


@super_admin_required
def franchise_admin_players(request, admin_id):
    """List all players under this franchise admin (worker=admin_id)."""
    try:
        admin_user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Franchise admin not found.')
        return redirect('franchise_balance')
    try:
        page_number = int(request.GET.get('pg', 1))
    except (ValueError, TypeError):
        page_number = 1
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '')
    players_query = User.objects.filter(worker=admin_user, is_staff=False).select_related('worker')
    if status_filter == 'active':
        players_query = players_query.filter(is_active=True)
    elif status_filter == 'inactive':
        players_query = players_query.filter(is_active=False)
    if search_query:
        players_query = players_query.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    players_query = players_query.order_by('-date_joined')
    paginator = Paginator(players_query, 20)
    try:
        page_obj = paginator.get_page(page_number)
    except Exception:
        page_obj = paginator.get_page(1)
    context = get_admin_context(request, {
        'admin_user': admin_user,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'page': 'franchise-balance',
    })
    return render(request, 'admin/franchise_admin_players.html', context)


@super_admin_required
def edit_franchise_admin(request, admin_id):
    """Edit franchise owner menu permissions only (from Franchise Balance → Edit privileges)."""
    try:
        user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Franchise admin not found.')
        return redirect('franchise_balance')
    try:
        permissions = AdminPermissions.objects.get(user=user)
    except AdminPermissions.DoesNotExist:
        permissions = AdminPermissions.objects.create(user=user)
    if request.method == 'POST':
        permissions.can_view_dashboard = request.POST.get('can_view_dashboard') == 'on'
        permissions.can_control_dice = request.POST.get('can_control_dice') == 'on'
        permissions.can_view_recent_rounds = request.POST.get('can_view_recent_rounds') == 'on'
        permissions.can_view_all_bets = request.POST.get('can_view_all_bets') == 'on'
        permissions.can_view_wallets = request.POST.get('can_view_wallets') == 'on'
        permissions.can_view_players = request.POST.get('can_view_players') == 'on'
        permissions.can_view_deposit_requests = request.POST.get('can_view_deposit_requests') == 'on'
        permissions.can_view_withdraw_requests = request.POST.get('can_view_withdraw_requests') == 'on'
        permissions.can_view_transactions = request.POST.get('can_view_transactions') == 'on'
        permissions.can_view_game_history = request.POST.get('can_view_game_history', 'on') == 'on'
        permissions.can_view_game_settings = request.POST.get('can_view_game_settings') == 'on'
        permissions.can_view_help_center = request.POST.get('can_view_help_center') == 'on'
        permissions.can_view_white_label = request.POST.get('can_view_white_label') == 'on'
        permissions.can_view_admin_management = request.POST.get('can_view_admin_management') == 'on'
        permissions.can_manage_payment_methods = request.POST.get('can_manage_payment_methods') == 'on'
        permissions.save()
        invalidate_admin_permissions_cache(user)
        messages.success(request, f'Privileges for "{user.username}" updated.')
        return redirect('franchise_balance')
    context = get_admin_context(request, {
        'admin_user': user,
        'permissions': permissions,
        'page': 'franchise-balance',
    })
    return render(request, 'admin/edit_franchise_admin.html', context)


@super_admin_required
def create_franchise_admin(request):
    """Create a franchise owner (admin) - appears only in Franchise Balance list, not in Worker Management."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2') or request.POST.get('confirm_password') or ''
        permissions = {
            'can_view_dashboard': request.POST.get('can_view_dashboard') == 'on',
            'can_control_dice': request.POST.get('can_control_dice') == 'on',
            'can_view_recent_rounds': request.POST.get('can_view_recent_rounds') == 'on',
            'can_view_all_bets': request.POST.get('can_view_all_bets') == 'on',
            'can_view_wallets': request.POST.get('can_view_wallets') == 'on',
            'can_view_players': request.POST.get('can_view_players') == 'on',
            'can_view_deposit_requests': request.POST.get('can_view_deposit_requests') == 'on',
            'can_view_withdraw_requests': request.POST.get('can_view_withdraw_requests') == 'on',
            'can_view_transactions': request.POST.get('can_view_transactions') == 'on',
            'can_view_game_history': request.POST.get('can_view_game_history', 'on') == 'on',
            'can_view_game_settings': request.POST.get('can_view_game_settings') == 'on',
            'can_view_help_center': request.POST.get('can_view_help_center') == 'on',
            'can_view_white_label': request.POST.get('can_view_white_label') == 'on',
            'can_view_admin_management': request.POST.get('can_view_admin_management') == 'on',
            'can_manage_payment_methods': request.POST.get('can_manage_payment_methods') == 'on',
        }
        if not username or not password:
            messages.error(request, 'Username and password are required.')
            return render(request, 'admin/create_franchise_admin.html', {'permissions': permissions})
        if password != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'admin/create_franchise_admin.html', {'permissions': permissions})
        if len(password) < 4:
            messages.error(request, 'Password must be at least 4 characters long.')
            return render(request, 'admin/create_franchise_admin.html', {'permissions': permissions})
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'admin/create_franchise_admin.html', {'permissions': permissions})
        try:
            email = f"{username}@gundu.ata"
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True,
                is_superuser=False,
                is_active=True,
                is_franchise_only=True,
            )
            AdminPermissions.objects.create(user=user, **permissions)
            invalidate_admin_permissions_cache(user)
            if request.POST.get('password_auto_generated', 'false') == 'true':
                messages.success(request, f'Franchise admin "{username}" created. They will appear only in Franchise Balance. 🔐 Save the password securely.')
            else:
                messages.success(request, f'Franchise admin "{username}" created. They will appear only in Franchise Balance.')
            return redirect('franchise_balance')
        except Exception as e:
            messages.error(request, f'Error creating franchise admin: {str(e)}')
            return render(request, 'admin/create_franchise_admin.html', {'permissions': permissions})
    return render(request, 'admin/create_franchise_admin.html', {})


@admin_required
def edit_admin(request, admin_id):
    """Edit worker permissions. Franchise owners can only edit workers under them."""
    if not _can_access_worker_management(request.user):
        messages.error(request, 'You do not have permission to access Worker Management.')
        return redirect('admin_dashboard')
    try:
        user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Admin user not found.')
        return redirect('admin_management')
    # Franchise owner can only edit workers who work under them
    if not is_super_admin(request.user) and getattr(user, 'works_under_id', None) != request.user.id:
        messages.error(request, 'You can only edit workers assigned to you.')
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
        permissions.can_view_withdraw_requests = request.POST.get('can_view_withdraw_requests') == 'on'
        permissions.can_view_transactions = request.POST.get('can_view_transactions') == 'on'
        permissions.can_view_game_history = request.POST.get('can_view_game_history', 'on') == 'on'
        permissions.can_view_game_settings = request.POST.get('can_view_game_settings') == 'on'
        permissions.can_view_help_center = request.POST.get('can_view_help_center') == 'on'
        permissions.can_view_white_label = request.POST.get('can_view_white_label') == 'on'
        permissions.can_view_admin_management = request.POST.get('can_view_admin_management') == 'on'
        permissions.can_manage_payment_methods = request.POST.get('can_manage_payment_methods') == 'on'
        permissions.save()
        invalidate_admin_permissions_cache(user)
        # Only Super Admin can change works_under; franchise owner's workers stay under them
        if is_super_admin(request.user):
            works_under_id = request.POST.get('works_under_id', '').strip()
            if works_under_id:
                try:
                    admin_user = User.objects.get(pk=int(works_under_id), is_staff=True)
                    user.works_under = admin_user if admin_user.id != user.id else None
                    user.save(update_fields=['works_under_id'])
                except (ValueError, User.DoesNotExist):
                    user.works_under = None
                    user.save(update_fields=['works_under_id'])
            else:
                if user.works_under_id:
                    user.works_under = None
                    user.save(update_fields=['works_under_id'])
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
        'queue_owners': _get_queue_owners_for_request(request),
    })
    return render(request, 'admin/edit_admin.html', context)


@admin_required
def delete_admin(request, admin_id):
    """Delete worker and redistribute their players. Franchise owners can only delete workers under them."""
    if not _can_access_worker_management(request.user):
        messages.error(request, 'You do not have permission to access Worker Management.')
        return redirect('admin_dashboard')
    try:
        user = User.objects.get(id=admin_id, is_staff=True)
    except User.DoesNotExist:
        messages.error(request, 'Worker not found.')
        return redirect('admin_management')
    if not is_super_admin(request.user) and getattr(user, 'works_under_id', None) != request.user.id:
        messages.error(request, 'You can only delete workers assigned to you.')
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
        messages.success(request, f'Worker "{username}" deleted successfully! {player_count} players redistributed among remaining workers.')
    else:
        messages.success(request, f'Worker "{username}" deleted successfully!')
    return redirect('admin_management')

@login_required(login_url='/game-admin/login/')
@admin_required
def manage_players(request):
    """Actual game players management page. Players assigned to admins only (not super admins)."""
    if not has_menu_permission(request.user, 'players'):
        messages.error(request, 'You do not have permission to view players.')
        return redirect('admin_dashboard')

    # Get status filter from query params
    status_filter = request.GET.get('status', 'all')
    try:
        page_number = int(request.GET.get('pg', 1))
    except (ValueError, TypeError):
        page_number = 1
    search_query = request.GET.get('search', '')
    
    # Build query - only show actual players (not staff), prefetch worker for display
    effective_admin = get_effective_admin(request.user)
    users_query = User.objects.filter(is_staff=False).select_related('worker')
    if not is_super_admin(effective_admin):
        users_query = users_query.filter(worker=effective_admin)
    
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
    
    # Statistics (same scope as list)
    base_players = User.objects.filter(is_staff=False)
    if not is_super_admin(effective_admin):
        base_players = base_players.filter(worker=effective_admin)
    total_users = base_players.count()
    active_users = base_players.filter(is_active=True).count()
    inactive_users = base_players.filter(is_active=False).count()

    is_franchise_scope = not is_super_admin(effective_admin)
    context = get_admin_context(request, {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'page': 'manage-players',
        'is_franchise_scope': is_franchise_scope,
        'scope_label': 'Your franchise' if is_franchise_scope else None,
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
            'description': 'When ticked: users cannot use the APK until they update. The update screen cannot be dismissed.'
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


def _normalize_help_phone(raw: str) -> str:
    """Keep leading '+' and digits only; accept any country code."""
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


@login_required(login_url='/game-admin/login/')
@admin_required
def help_center(request):
    """Help Center: Super Admin sets global defaults; franchise owners set their own (per-franchise) numbers."""
    if not has_menu_permission(request.user, 'help_center'):
        messages.error(request, 'You do not have permission to access Help Center settings.')
        return redirect('admin_dashboard')

    effective_admin = get_effective_admin(request.user)
    global_whatsapp = get_game_setting('SUPPORT_WHATSAPP_NUMBER', '')
    global_telegram = get_game_setting('SUPPORT_TELEGRAM', '')

    if is_super_admin(effective_admin):
        whatsapp_number = global_whatsapp
        telegram_number = global_telegram
        is_franchise_scope = False
    else:
        try:
            fb = FranchiseBalance.objects.get(user=effective_admin)
            whatsapp_number = (fb.help_whatsapp_number or '').strip() or global_whatsapp
            telegram_number = (fb.help_telegram or '').strip() or global_telegram
        except FranchiseBalance.DoesNotExist:
            fb = None
            whatsapp_number = global_whatsapp
            telegram_number = global_telegram
        is_franchise_scope = True

    if request.method == 'POST':
        whatsapp_number = _normalize_help_phone(request.POST.get('SUPPORT_WHATSAPP_NUMBER'))
        telegram_number = _normalize_help_phone(request.POST.get('SUPPORT_TELEGRAM'))

        if is_super_admin(effective_admin):
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
            messages.success(request, 'Global Help Center contacts updated successfully.')
        else:
            fb, _ = FranchiseBalance.objects.get_or_create(
                user=effective_admin,
                defaults={'balance': 0}
            )
            fb.help_whatsapp_number = whatsapp_number
            fb.help_telegram = telegram_number
            fb.save()
            messages.success(request, 'Your franchise Help Center contacts updated. Players under your franchise will see these numbers when they use the app with your package.')

        return redirect('help_center')

    context = get_admin_context(request, {
        'page': 'help_center',
        'whatsapp_number': whatsapp_number,
        'telegram_number': telegram_number,
        'admin_profile': get_admin_profile(request.user),
        'is_franchise_scope': is_franchise_scope,
        'scope_label': 'Your franchise' if is_franchise_scope else None,
    })
    return render(request, 'admin/help_center.html', context)


@login_required(login_url='/game-admin/login/')
@admin_required
def white_label_leads(request):
    """List White Label lead submissions"""
    if not has_menu_permission(request.user, 'white_label'):
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
    """List payment methods. Super admin sees global (owner=null); franchise owners see only their own."""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    effective_admin = get_effective_admin(request.user)
    if is_super_admin(effective_admin):
        methods_qs = PaymentMethod.objects.filter(owner__isnull=True)
    else:
        methods_qs = PaymentMethod.objects.filter(owner=effective_admin)

    # Create default payment methods only for super admin when no global methods exist
    if is_super_admin(effective_admin) and not PaymentMethod.objects.filter(owner__isnull=True).exists():
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
            PaymentMethod.objects.create(owner=None, **method_data)

        messages.info(request, 'Created default payment methods. Please edit them with your actual payment details.')
        return redirect('payment_methods')

    methods = methods_qs.order_by('-is_active', 'method_type')

    # Get available method types (exclude already used ones within this scope)
    used_method_types = set(methods.values_list('method_type', flat=True))
    all_method_choices = PaymentMethod.METHOD_TYPES

    # Filter out already used method types
    available_method_types = [mt for mt in all_method_choices if mt[0] not in used_method_types]

    is_franchise_scope = not is_super_admin(effective_admin)
    context = get_admin_context(request, {
        'payment_methods': methods,
        'available_method_types': available_method_types,
        'page': 'payment-methods',
        'is_franchise_scope': is_franchise_scope,
        'scope_label': 'Your franchise' if is_franchise_scope else None,
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

        effective_admin = get_effective_admin(request.user)
        owner_for_create = None if is_super_admin(effective_admin) else effective_admin
        scope_qs = PaymentMethod.objects.filter(owner=owner_for_create) if owner_for_create is not None else PaymentMethod.objects.filter(owner__isnull=True)
        if scope_qs.filter(method_type=method_type).exists():
            messages.error(request, 'This payment method type is already in use in your list.')
            return redirect('payment_methods')

        method_type_display = dict(PaymentMethod.METHOD_TYPES).get(method_type, method_type)

        try:
            import re
            clean_rate = re.sub(r'[^\d.]', '', str(usdt_exchange_rate))
            if not clean_rate or clean_rate == '.':
                clean_rate = '90.00'
            
            PaymentMethod.objects.create(
                owner=owner_for_create,
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
    """Edit a payment method. Franchise can only edit their own."""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    effective_admin = get_effective_admin(request.user)
    if is_super_admin(effective_admin):
        method = get_object_or_404(PaymentMethod, pk=pk, owner__isnull=True)
    else:
        method = get_object_or_404(PaymentMethod, pk=pk, owner=effective_admin)

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
    """Delete a payment method. Franchise can only delete their own."""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    if request.method == 'POST':
        effective_admin = get_effective_admin(request.user)
        if is_super_admin(effective_admin):
            method = get_object_or_404(PaymentMethod, pk=pk, owner__isnull=True)
        else:
            method = get_object_or_404(PaymentMethod, pk=pk, owner=effective_admin)
        name = method.name

        try:
            method.delete()
            messages.success(request, f'Payment method "{name}" deleted successfully!')
        except Exception as e:
            messages.error(request, f'Error deleting payment method: {str(e)}')

    return redirect('payment_methods')


@admin_required
def toggle_payment_method(request, pk):
    """Toggle active status of a payment method. Franchise can only toggle their own."""
    if not has_menu_permission(request.user, 'payment_methods'):
        messages.error(request, 'You do not have permission to manage payment methods.')
        return redirect('admin_dashboard')

    effective_admin = get_effective_admin(request.user)
    if is_super_admin(effective_admin):
        method = get_object_or_404(PaymentMethod, pk=pk, owner__isnull=True)
    else:
        method = get_object_or_404(PaymentMethod, pk=pk, owner=effective_admin)
    method.is_active = not method.is_active
    method.save()
    
    status = "activated" if method.is_active else "deactivated"
    messages.success(request, f'Payment method "{method.name}" {status} successfully!')
    return redirect('payment_methods')


# ─── Live Stream (HLS via MediaRecorder chunks → ffmpeg) ─────────────────────

import subprocess
import os as _os


def _get_hls_dir():
    from django.conf import settings as _s
    d = _os.path.join(_s.MEDIA_ROOT, 'hls')
    _os.makedirs(d, exist_ok=True)
    return d


def _kill_ffmpeg():
    hls_dir = _get_hls_dir()
    pid_file = _os.path.join(hls_dir, 'ffmpeg.pid')
    if _os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            _os.kill(pid, 9)
        except Exception:
            pass
        try:
            _os.remove(pid_file)
        except Exception:
            pass


@admin_required
def livestream_broadcast(request):
    stream, _ = LiveStream.objects.get_or_create(id=1, defaults={'title': 'Live Stream'})
    context = get_admin_context(request)
    context['stream'] = stream
    return render(request, 'admin/livestream_broadcast.html', context)


def livestream_watch(request):
    stream = LiveStream.objects.filter(id=1).first()
    return render(request, 'admin/livestream_watch.html', {'stream': stream})


def users_live(request):
    return render(request, 'admin/users_live.html')


@csrf_exempt
@admin_required
@require_POST
def livestream_start(request):
    """Clear HLS dir, mark stream live."""
    hls_dir = _get_hls_dir()
    _kill_ffmpeg()
    for f in _os.listdir(hls_dir):
        try:
            _os.remove(_os.path.join(hls_dir, f))
        except Exception:
            pass
    stream, _ = LiveStream.objects.get_or_create(id=1)
    stream.is_live = True
    stream.offer_sdp = '0'
    stream.save()
    return JsonResponse({'ok': True})


@csrf_exempt
@admin_required
@require_POST
def livestream_stop(request):
    _kill_ffmpeg()
    stream = LiveStream.objects.filter(id=1).first()
    if stream:
        stream.is_live = False
        stream.save()
    hls_dir = _get_hls_dir()
    playlist_path = _os.path.join(hls_dir, 'stream.m3u8')
    if _os.path.exists(playlist_path):
        with open(playlist_path, 'a') as f:
            f.write('#EXT-X-ENDLIST\n')
    return JsonResponse({'ok': True})


@csrf_exempt
@admin_required
@require_POST
def livestream_chunk(request):
    chunk_file = request.FILES.get('chunk') or request.FILES.get('video')
    if not chunk_file:
        return JsonResponse({'error': 'no chunk'}, status=400)

    hls_dir = _get_hls_dir()
    stream = LiveStream.objects.filter(id=1).first()
    if not stream or not stream.is_live:
        return JsonResponse({'error': 'not live'}, status=400)

    try:
        n = int(stream.offer_sdp or '0')
    except ValueError:
        n = 0
    n += 1
    stream.offer_sdp = str(n)
    stream.save(update_fields=['offer_sdp'])

    chunk_path = _os.path.join(hls_dir, f'chunk_{n:05d}.webm')
    with open(chunk_path, 'wb') as f:
        for part in chunk_file.chunks():
            f.write(part)

    ts_path = _os.path.join(hls_dir, f'seg{n:05d}.ts')
    cmd = [
        'ffmpeg', '-y',
        '-i', chunk_path,
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-crf', '23',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '2',
        '-f', 'mpegts',
        ts_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)

    try:
        _os.remove(chunk_path)
    except Exception:
        pass

    if result.returncode != 0:
        err = result.stderr.decode()[-400:]
        return JsonResponse({'error': 'ffmpeg failed', 'detail': err}, status=500)

    ts_files = sorted(f for f in _os.listdir(hls_dir) if f.endswith('.ts'))
    if len(ts_files) > 6:
        for old in ts_files[:-6]:
            try:
                _os.remove(_os.path.join(hls_dir, old))
            except Exception:
                pass
        ts_files = ts_files[-6:]

    dur_result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', ts_path],
        capture_output=True, text=True
    )
    try:
        seg_duration = float(dur_result.stdout.strip())
    except Exception:
        seg_duration = 8.0

    seq = max(0, n - len(ts_files))
    playlist_path = _os.path.join(hls_dir, 'stream.m3u8')
    lines = [
        '#EXTM3U',
        '#EXT-X-VERSION:3',
        f'#EXT-X-TARGETDURATION:{int(seg_duration) + 2}',
        f'#EXT-X-MEDIA-SEQUENCE:{seq}',
    ]
    for ts in ts_files:
        lines.append(f'#EXTINF:{seg_duration:.3f},')
        lines.append(f'/media/hls/{ts}')
    tmp = playlist_path + '.tmp'
    with open(tmp, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    _os.replace(tmp, playlist_path)

    hls_ready = len(ts_files) >= 2
    return JsonResponse({'ok': True, 'chunk': n, 'segments': len(ts_files), 'hls_ready': hls_ready})


def livestream_status(request):
    stream = LiveStream.objects.filter(id=1).first()
    is_live = bool(stream and stream.is_live)
    hls_dir = _get_hls_dir()
    playlist = _os.path.join(hls_dir, 'stream.m3u8')
    ts_count = len([f for f in _os.listdir(hls_dir) if f.endswith('.ts')]) if _os.path.exists(hls_dir) else 0
    hls_ready = _os.path.exists(playlist) and ts_count >= 2
    return JsonResponse({'live': is_live, 'hls_ready': hls_ready and is_live, 'segments': ts_count})


def livestream_signal(request):
    return JsonResponse({'ok': True})


def livestream_viewer_signal(request):
    return JsonResponse({'live': False})
