from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib import messages
from .models import User, Wallet, Transaction, DepositRequest, PaymentMethod


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'phone_number', 'is_active', 'created_at']
    list_filter = ['is_active', 'is_staff', 'created_at']
    search_fields = ['username', 'email', 'phone_number']
    
    def delete_model(self, request, obj):
        """Override delete to prevent accidental deletion of regular users"""
        # Only allow deletion of admin users (is_staff=True) and only if not superuser
        if obj.is_staff and not obj.is_superuser:
            # This is an admin user, allow deletion
            super().delete_model(request, obj)
        elif obj.is_superuser:
            messages.error(request, f'Cannot delete Super Admin user "{obj.username}".')
        else:
            # Regular user - prevent deletion from Django admin
            messages.error(request, f'Regular users cannot be deleted from Django Admin. Use the custom admin panel if needed.')
    
    def delete_queryset(self, request, queryset):
        """Override bulk delete to prevent accidental deletion of regular users"""
        # Filter out regular users and superusers
        admin_users = queryset.filter(is_staff=True, is_superuser=False)
        regular_users = queryset.filter(is_staff=False)
        superusers = queryset.filter(is_superuser=True)
        
        deleted_count = 0
        if admin_users.exists():
            for obj in admin_users:
                self.delete_model(request, obj)
                deleted_count += 1
        
        if regular_users.exists():
            messages.warning(request, f'Skipped {regular_users.count()} regular user(s). Regular users cannot be deleted from Django Admin.')
        
        if superusers.exists():
            messages.warning(request, f'Skipped {superusers.count()} superuser(s). Superusers cannot be deleted.')
        
        if deleted_count > 0:
            messages.success(request, f'Deleted {deleted_count} admin user(s).')


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'bonus_balance', 'unavaliable_balance', 'created_at', 'updated_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'transaction_type', 'amount', 'balance_before', 'balance_after', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['user__username']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'


@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'status', 'created_at', 'processed_by']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'payment_reference']
    readonly_fields = ['created_at', 'updated_at', 'processed_at']


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'method_type', 'is_active', 'created_at']
    list_filter = ['method_type', 'is_active']
    search_fields = ['name', 'upi_id', 'account_number']




