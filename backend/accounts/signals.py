"""
Django signals for automatic player distribution and notifications
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import User, DepositRequest, WithdrawRequest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .player_distribution import (
    assign_player_to_admin,
    redistribute_players_from_deleted_admin,
    balance_player_distribution
)


@receiver(post_save, sender=DepositRequest)
def notify_admin_deposit_request(sender, instance, created, **kwargs):
    """Notify admins when a new deposit request is created"""
    if created:
        channel_layer = get_channel_layer()
        screenshot_url = None
        try:
            if instance.screenshot:
                screenshot_url = instance.screenshot.url
        except:
            pass
            
        async_to_sync(channel_layer.group_send)(
            'admin_notifications',
            {
                'type': 'admin_notification',
                'notification_type': 'deposit',
                'id': instance.id,
                'user_id': instance.user.id,
                'worker_id': instance.user.worker.id if instance.user.worker else None,
                'user': instance.user.username,
                'amount': float(instance.amount),
                'screenshot_url': screenshot_url,
                'payment_reference': instance.payment_reference or '',
                'created_at': instance.created_at.strftime("%b %d, %H:%M"),
            }
        )


@receiver(post_save, sender=WithdrawRequest)
def notify_admin_withdraw_request(sender, instance, created, **kwargs):
    """Notify admins when a new withdraw request is created"""
    if created:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'admin_notifications',
            {
                'type': 'admin_notification',
                'notification_type': 'withdraw',
                'id': instance.id,
                'user_id': instance.user.id,
                'worker_id': instance.user.worker.id if instance.user.worker else None,
                'user': instance.user.username,
                'amount': float(instance.amount),
                'method': instance.withdrawal_method or '',
                'details': instance.withdrawal_details or '',
                'created_at': instance.created_at.strftime("%b %d, %H:%M"),
            }
        )
