from django.db import models
from django.conf import settings
from decimal import Decimal


class GameRound(models.Model):
    """Game round model"""
    ROUND_STATUS = [
        ('WAITING', 'Waiting'),
        ('BETTING', 'Betting Open'),
        ('CLOSED', 'Betting Closed'),
        ('RESULT', 'Result Announced'),
        ('COMPLETED', 'Completed'),
    ]

    round_id = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=10, choices=ROUND_STATUS, default='WAITING')
    dice_result = models.CharField(max_length=50, null=True, blank=True)  # Stores winning number(s) as comma-separated string
    dice_1 = models.IntegerField(null=True, blank=True)  # Individual dice values (1-6)
    dice_2 = models.IntegerField(null=True, blank=True)
    dice_3 = models.IntegerField(null=True, blank=True)
    dice_4 = models.IntegerField(null=True, blank=True)
    dice_5 = models.IntegerField(null=True, blank=True)
    dice_6 = models.IntegerField(null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    betting_close_time = models.DateTimeField(null=True, blank=True)
    result_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    total_bets = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Timing settings for this specific round (stored when round is created)
    betting_close_seconds = models.IntegerField(default=30)  # Time when betting closes
    dice_roll_seconds = models.IntegerField(default=7)  # Time before dice result when warning is sent
    dice_result_seconds = models.IntegerField(default=51)  # Time when dice result is announced
    round_end_seconds = models.IntegerField(default=70)  # Total round duration

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"Round {self.round_id} - {self.status}"

    @property
    def dice_result_list(self):
        """Returns dice_result as a list of strings"""
        if not self.dice_result:
            return []
        return [r.strip() for r in str(self.dice_result).split(',') if r.strip()]


class Bet(models.Model):
    """Bet model"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bets')
    round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name='bets')
    number = models.IntegerField()  # 1-6
    chip_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payout_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # Removed unique_together constraint to allow multiple independent bets on same number

    def __str__(self):
        return f"{self.user.username} - Round {self.round.round_id} - Number {self.number} - {self.chip_amount}"


class DiceResult(models.Model):
    """Dice result history"""
    round = models.OneToOneField(GameRound, on_delete=models.CASCADE, related_name='dice_result_record')
    result = models.CharField(max_length=50)  # Stores winning number(s) as comma-separated string
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='dice_results_set')
    set_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Round {self.round.round_id} - Result: {self.result}"


class GameSettings(models.Model):
    """Game configuration settings"""
    key = models.CharField(max_length=50, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}: {self.value}"


class RoundPrediction(models.Model):
    """User predictions/guesses after betting closes (no money involved)"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='round_predictions')
    round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name='predictions')
    number = models.IntegerField()  # 1-6
    is_correct = models.BooleanField(default=False)  # Set to True if prediction matches result
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('user', 'round')]  # One prediction per user per round

    def __str__(self):
        return f"{self.user.username} - Round {self.round.round_id} - Predicted {self.number}"


class AdminPermissions(models.Model):
    """Admin user permissions for menu access"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_permissions')
    
    # Menu permissions
    can_view_dashboard = models.BooleanField(default=True)
    can_control_dice = models.BooleanField(default=True)
    can_view_recent_rounds = models.BooleanField(default=True)
    can_view_all_bets = models.BooleanField(default=True)
    can_view_wallets = models.BooleanField(default=True)
    can_view_players = models.BooleanField(default=True)
    can_view_deposit_requests = models.BooleanField(default=True)
    can_view_withdraw_requests = models.BooleanField(default=True)
    can_view_transactions = models.BooleanField(default=True)
    can_view_game_settings = models.BooleanField(default=False)  # Super Admin only by default
    can_view_admin_management = models.BooleanField(default=False)  # Super Admin only by default
    can_manage_payment_methods = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Permissions for {self.user.username}"
    
    def get_permissions_dict(self):
        """Return permissions as dictionary"""
        return {
            'dashboard': self.can_view_dashboard,
            'dice_control': self.can_control_dice,
            'recent_rounds': self.can_view_recent_rounds,
            'all_bets': self.can_view_all_bets,
            'wallets': self.can_view_wallets,
            'players': self.can_view_players,
            'deposit_requests': self.can_view_deposit_requests,
            'withdraw_requests': self.can_view_withdraw_requests,
            'transactions': self.can_view_transactions,
            'game_settings': self.can_view_game_settings,
            'admin_management': self.can_view_admin_management,
            'payment_methods': self.can_manage_payment_methods,
        }

