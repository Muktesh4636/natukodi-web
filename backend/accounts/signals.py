"""
Django signals for automatic player distribution and notifications
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import User, DepositRequest, WithdrawRequest, Wallet
from .player_distribution import (
    assign_player_to_admin,
    redistribute_players_from_deleted_admin,
    balance_player_distribution
)
import json


@receiver(post_save, sender=DepositRequest)
def notify_admin_deposit_request(sender, instance, created, **kwargs):
    """Deposit created (real-time WebSocket notifications removed)."""
    if created:
        pass


@receiver(post_save, sender=WithdrawRequest)
def notify_admin_withdraw_request(sender, instance, created, **kwargs):
    """Withdraw created (real-time WebSocket notifications removed)."""
    if created:
        pass


@receiver(post_save, sender=Wallet)
def sync_wallet_balance_to_redis(sender, instance, **kwargs):
    """
    Keep Redis balance cache consistent with DB wallet updates.

    Why:
    - Mobile app APIs are Redis-first for `user_balance:{user_id}`.
    - Django admin edits update Postgres but previously did NOT update Redis,
      so users kept seeing stale balances until TTL expiry / next login.
    """
    try:
        from game.utils import get_redis_client

        redis_client = get_redis_client()
        if not redis_client:
            return

        user_id = instance.user_id
        balance_str = str(instance.balance)

        # 1) Wallet cache used by WalletView and other APIs
        redis_client.set(f"user_balance:{user_id}", balance_str, ex=86400)

        # 2) Smart dice player state may use current_balance; keep in sync if present
        ps_key = f"player_state:{user_id}"
        ps_raw = redis_client.get(ps_key)
        if ps_raw:
            try:
                state = json.loads(ps_raw) if isinstance(ps_raw, str) else json.loads(str(ps_raw))
                state["current_balance"] = int(instance.balance)
                redis_client.set(ps_key, json.dumps(state), ex=86400)
            except Exception:
                # If state isn't JSON, don't break wallet save.
                pass
    except Exception:
        # Never block DB saves due to Redis problems.
        return
