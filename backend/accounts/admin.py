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
        """Allow deletion of all users except superusers"""
        if obj.is_superuser:
            messages.error(request, f'Cannot delete Super Admin user "{obj.username}".')
        else:
            super().delete_model(request, obj)
    
    def delete_queryset(self, request, queryset):
        """Bulk delete - allow all except superusers"""
        to_delete = queryset.exclude(is_superuser=True)
        superusers = queryset.filter(is_superuser=True)
        
        if superusers.exists():
            messages.warning(request, f'Skipped {superusers.count()} superuser(s). Superusers cannot be deleted.')
        
        if to_delete.exists():
            deleted_count, _ = to_delete.delete()
            messages.success(request, f'Successfully deleted {deleted_count} user(s).')


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'unavaliable_balance', 'created_at', 'updated_at']
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




