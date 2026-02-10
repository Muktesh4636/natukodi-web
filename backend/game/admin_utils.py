from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
try:
    from accounts.models import AdminProfile
except ImportError:
    AdminProfile = None


def is_staff(user):
    """Check if user is staff"""
    return user.is_authenticated and user.is_staff


def is_super_admin(user):
    """Check if user is superuser"""
    return user.is_authenticated and user.is_superuser


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


def get_admin_permissions(user):
    """Get admin permissions for user"""
    if not user.is_authenticated:
        return None
    try:
        from .models import AdminPermissions
        return AdminPermissions.objects.get(user=user)
    except AdminPermissions.DoesNotExist:
        # Create default permissions if none exist
        if user.is_staff:
            from .models import AdminPermissions
            return AdminPermissions.objects.create(user=user)
        return None


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
        'game_settings': 'can_view_game_settings',
        'admin_management': 'can_view_admin_management',
        'payment_methods': 'can_manage_payment_methods',
    }
    
    field_name = permission_map.get(permission_name)
    if not field_name:
        return False
    
    return getattr(perms, field_name, False)


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
                return redirect('/admin/')
            return view_func(request, *args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f'Permission Error: {str(e)}')
            return redirect('/admin/')
    return wrapper


def super_admin_required(view_func):
    """Decorator to require super admin access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_super_admin(request.user):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('/admin/')
        return view_func(request, *args, **kwargs)
    return wrapper


def permission_required(permission_name):
    """Decorator factory to require specific permission"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not has_permission(request.user, permission_name):
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('/admin/')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

