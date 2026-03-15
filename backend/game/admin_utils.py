from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
try:
    from accounts.models import AdminProfile
except ImportError:
    AdminProfile = None

# Cache TTL for admin permissions (reduces DB hits on every admin page load; helps avoid 504)
ADMIN_PERMS_CACHE_TTL = 60
ADMIN_PERMS_CACHE_KEY_PREFIX = 'admin_perms_'


class _CachedPermissions:
    """Thin wrapper so has_menu_permission can use getattr(perms, field_name)."""
    __slots__ = ('_data',)
    def __init__(self, data):
        self._data = data or {}
    def __getattr__(self, name):
        return self._data.get(name, False)


def is_staff(user):
    """Check if user is staff"""
    return user.is_authenticated and user.is_staff


def is_super_admin(user):
    """Check if user is superuser"""
    return user.is_authenticated and user.is_superuser


def get_effective_admin(user):
    """
    Return the admin whose deposit/withdraw queue this user sees.
    - If user has works_under set (worker assigned to an admin), return that admin.
    - Otherwise return user (franchise admin sees own queue; Super Admin sees all).
    """
    if not user or not user.is_authenticated:
        return user
    works_under_id = getattr(user, 'works_under_id', None)
    if works_under_id:
        from accounts.models import User as UserModel
        try:
            return UserModel.objects.get(pk=works_under_id)
        except UserModel.DoesNotExist:
            pass
    return user


def is_admin(user):
    """Check if user is admin (staff or has admin profile)"""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if AdminProfile:
        try:
            admin_profile = AdminProfile.objects.get(user=user)
            return admin_profile.is_active
        except AdminProfile.DoesNotExist:
            return False
    return False


def has_permission(user, permission_name):
    """Check if user has specific permission"""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if AdminProfile:
        try:
            admin_profile = AdminProfile.objects.get(user=user)
            if not admin_profile.is_active:
                return False
            # Check specific permissions based on permission_name
            if permission_name == 'view_dashboard':
                return admin_profile.can_view_dashboard
            elif permission_name == 'control_dice':
                return admin_profile.can_control_dice
            elif permission_name == 'manage_users':
                return admin_profile.can_manage_users
            elif permission_name == 'manage_deposits':
                return admin_profile.can_manage_deposits
            return False
        except AdminProfile.DoesNotExist:
            return user.is_staff
    return user.is_staff


def get_admin_profile(user):
    """Get admin profile for user"""
    if not user.is_authenticated or not AdminProfile:
        return None
    try:
        return AdminProfile.objects.get(user=user)
    except AdminProfile.DoesNotExist:
        return None


def _perms_to_dict(perms):
    """Build a dict of permission flags for caching."""
    return {
        'can_view_dashboard': getattr(perms, 'can_view_dashboard', False),
        'can_control_dice': getattr(perms, 'can_control_dice', False),
        'can_view_recent_rounds': getattr(perms, 'can_view_recent_rounds', False),
        'can_view_all_bets': getattr(perms, 'can_view_all_bets', False),
        'can_view_wallets': getattr(perms, 'can_view_wallets', False),
        'can_view_players': getattr(perms, 'can_view_players', False),
        'can_view_deposit_requests': getattr(perms, 'can_view_deposit_requests', False),
        'can_view_withdraw_requests': getattr(perms, 'can_view_withdraw_requests', False),
        'can_view_transactions': getattr(perms, 'can_view_transactions', False),
        'can_view_game_history': getattr(perms, 'can_view_game_history', True),
        'can_view_game_settings': getattr(perms, 'can_view_game_settings', False),
        'can_view_help_center': getattr(perms, 'can_view_help_center', False),
        'can_view_white_label': getattr(perms, 'can_view_white_label', False),
        'can_view_admin_management': getattr(perms, 'can_view_admin_management', False),
        'can_manage_payment_methods': getattr(perms, 'can_manage_payment_methods', False),
    }


def get_admin_permissions(user):
    """Get admin permissions for user. Cached 60s per user to reduce DB load and 504 risk."""
    if not user.is_authenticated:
        return None
    cache_key = ADMIN_PERMS_CACHE_KEY_PREFIX + str(user.id)
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return _CachedPermissions(cached)
    except Exception:
        pass
    from .models import AdminPermissions
    try:
        perms = AdminPermissions.objects.get(user=user)
    except AdminPermissions.DoesNotExist:
        if user.is_staff:
            perms = AdminPermissions.objects.create(user=user)
        else:
            return None
    try:
        cache.set(cache_key, _perms_to_dict(perms), ADMIN_PERMS_CACHE_TTL)
    except Exception:
        pass
    return perms


def has_menu_permission(user, permission_name):
    """Check if user has permission to view a menu item"""
    # Super admins have all permissions
    if is_super_admin(user):
        return True
    
    # Get permissions
    perms = get_admin_permissions(user)
    if not perms:
        return False
    
    # Map permission names to model fields
    permission_map = {
        'dashboard': 'can_view_dashboard',
        'dice_control': 'can_control_dice',
        'recent_rounds': 'can_view_recent_rounds',
        'all_bets': 'can_view_all_bets',
        'wallets': 'can_view_wallets',
        'players': 'can_view_players',
        'deposit_requests': 'can_view_deposit_requests',
        'withdraw_requests': 'can_view_withdraw_requests',
        'transactions': 'can_view_transactions',
        'game_history': 'can_view_game_history',
        'game_settings': 'can_view_game_settings',
        'help_center': 'can_view_help_center',
        'white_label': 'can_view_white_label',
        'admin_management': 'can_view_admin_management',
        'payment_methods': 'can_manage_payment_methods',
    }
    
    field_name = permission_map.get(permission_name)
    if not field_name:
        return False
    
    return getattr(perms, field_name, False)


def invalidate_admin_permissions_cache(user):
    """Call after creating/updating AdminPermissions for a user so next request sees fresh perms."""
    if user is None:
        return
    try:
        cache.delete(ADMIN_PERMS_CACHE_KEY_PREFIX + str(user.id))
    except Exception:
        pass


def admin_required(view_func):
    """Decorator to require admin access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            if not request.user.is_authenticated:
                # Redirect to game admin login with next parameter
                from django.http import HttpResponseRedirect
                from django.urls import reverse
                try:
                    login_url = reverse('admin_login')
                except:
                    login_url = '/game-admin/login/'
                next_url = request.get_full_path()
                return HttpResponseRedirect(f'{login_url}?next={next_url}')
            if not is_admin(request.user):
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('admin_login')
            return view_func(request, *args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f'Permission Error: {str(e)}')
            return redirect('admin_login')
    return wrapper


def super_admin_required(view_func):
    """Decorator to require super admin access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_super_admin(request.user):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def permission_required(permission_name):
    """Decorator factory to require specific permission"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not has_permission(request.user, permission_name):
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('admin_login')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

