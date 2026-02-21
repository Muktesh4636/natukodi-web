from django.contrib.auth.models import AbstractUser
from django.db import models
from decimal import Decimal
from django.utils import timezone
import uuid
import string
import random


class User(AbstractUser):
    """Custom User model with additional fields"""
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    
    # New fields for personal data
    GENDER_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('OTHER', 'Other'),
    ]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
    telegram = models.CharField(max_length=100, null=True, blank=True)
    facebook = models.CharField(max_length=100, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    worker = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clients',
        limit_choices_to={'is_staff': True}
    )
    # Referral system
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals'
    )
    referral_code = models.CharField(max_length=20, unique=True, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.username
    
    def generate_unique_referral_code(self):
        """
        Generate a unique referral code for this user.
        Sequential numeric format starting from 123: 123, 124, 125, ...
        """
        # Find max existing numeric referral code
        codes = User.objects.exclude(
            referral_code__isnull=True
        ).exclude(
            referral_code=''
        ).values_list('referral_code', flat=True)
        numeric_vals = []
        for c in codes:
            if c and str(c).isdigit():
                numeric_vals.append(int(c))
        next_num = max(numeric_vals) + 1 if numeric_vals else 123
        next_num = max(next_num, 123)  # Ensure we start at least at 123

        # Handle collision (rare with concurrent requests)
        while User.objects.filter(referral_code=str(next_num)).exclude(pk=self.pk).exists():
            next_num += 1
        return str(next_num)
    
    def save(self, *args, **kwargs):
        # Ensure referral code is generated if missing
        # If it already exists, don't allow it to be overwritten by an empty value
        if not self.referral_code:
            self.referral_code = self.generate_unique_referral_code()
        super().save(*args, **kwargs)


class Wallet(models.Model):
    """User wallet for managing balance"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.BigIntegerField(default=0)
    unavaliable_balance = models.BigIntegerField(default=0, help_text="Amount currently locked or unavaliable for withdrawal")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(balance__gte=0),
                name='wallet_balance_non_negative'
            ),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.balance}"

    def deduct(self, amount):
        """Deduct amount from wallet (e.g. bet placed and lost).
        Withdrawable = turnover (amount wagered). Unavailable = balance - turnover.
        When we bet `amount`: balance -= amount, turnover += amount.
        So unavaliable = balance - turnover drops by 2*amount (balance-amount, turnover+amount).
        """
        if self.balance >= amount:
            # Reduce unavaliable by 2*amount so withdrawable increases by amount (turnover)
            release = min(self.unavaliable_balance, 2 * amount)
            self.unavaliable_balance -= release
            self.unavaliable_balance = max(0, self.unavaliable_balance)
            self.balance -= amount
            self.save()
            return True
        return False

    def add(self, amount, is_bonus=False):
        """Add amount to wallet. If is_bonus or deposit, add to unavaliable_balance too."""
        self.balance += amount
        if is_bonus:
            self.unavaliable_balance += amount
        self.save()
        return True

    @property
    def withdrawable_balance(self):
        """Calculate balance available for withdrawal"""
        return max(Decimal('0.00'), self.balance - self.unavaliable_balance)


class DailyReward(models.Model):
    """Daily reward spin for users"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_rewards')
    reward_amount = models.BigIntegerField(default=0)
    reward_type = models.CharField(max_length=20, choices=[
        ('MONEY', 'Money Reward'),
        ('TRY_AGAIN', 'Try Again'),
    ], default='MONEY')
    claimed_at = models.DateTimeField(auto_now_add=True)
    reward_date = models.DateField(default=timezone.now)

    class Meta:
        unique_together = ['user', 'reward_date']
        ordering = ['-claimed_at']

    def __str__(self):
        return f"{self.user.username} - {self.reward_amount} on {self.reward_date}"


class LuckyDraw(models.Model):
    """Lucky draw spin based on bank transfer deposits"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lucky_draws')
    deposit_request = models.ForeignKey('DepositRequest', on_delete=models.CASCADE, related_name='lucky_draws')
    reward_amount = models.BigIntegerField(default=0)
    deposit_amount = models.BigIntegerField()
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-claimed_at']

    def __str__(self):
        return f"{self.user.username} - ₹{self.reward_amount} from ₹{self.deposit_amount} deposit"


class Transaction(models.Model):
    """Transaction log for wallet operations"""
    TRANSACTION_TYPES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAW', 'Withdraw'),
        ('BET', 'Bet'),
        ('WIN', 'Win'),
        ('REFUND', 'Refund'),
        ('REFERRAL_BONUS', 'Referral Bonus'),
        ('MILESTONE_BONUS', 'Milestone Bonus'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.BigIntegerField()
    balance_before = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} - {self.amount}"


class DepositRequest(models.Model):
    """Manual deposit requests reviewed by admin"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.BigIntegerField()
    screenshot = models.ImageField(upload_to='deposit_screenshots/')
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True, blank=True, related_name='deposit_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    payment_link = models.URLField(blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name='processed_deposit_requests',
        on_delete=models.SET_NULL,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - ₹{self.amount} - {self.status}"


class WithdrawRequest(models.Model):
    """Manual withdraw requests reviewed by admin"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('COMPLETED', 'Payment Completed'),
        ('REJECTED', 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdraw_requests')
    amount = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    # Withdrawal details (e.g., UPI ID, Bank details)
    withdrawal_method = models.CharField(max_length=50, blank=True)
    withdrawal_details = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name='processed_withdraw_requests',
        on_delete=models.SET_NULL,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)
    utr_number = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - ₹{self.amount} - {self.status}"


class PaymentMethod(models.Model):
    """Admin-configured payment methods for deposits"""
    METHOD_TYPES = [
        ('PHONEPE', 'Phone Pe'),
        ('GPAY', 'Google Pay'),
        ('PAYTM', 'Paytm'),
        ('UPI', 'UPI'),
        ('BANK', 'Bank Account'),
        ('QR', 'QR'),
        ('USDT_TRC20', 'USDT (TRC20)'),
        ('USDT_BEP20', 'USDT (BEP20)'),
    ]

    name = models.CharField(max_length=100)
    method_type = models.CharField(max_length=20, choices=METHOD_TYPES)
    account_name = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    link = models.URLField(max_length=500, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    qr_image = models.ImageField(upload_to='payment_qr_codes/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    usdt_network = models.CharField(max_length=50, blank=True, null=True, default='')
    usdt_wallet_address = models.CharField(max_length=100, blank=True, null=True, default='')
    usdt_exchange_rate = models.BigIntegerField(default=90, help_text="1 USDT = X Rupees")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_method_type_display()} - {self.name}"


class UserBankDetail(models.Model):
    """User's saved bank and UPI details for withdrawals"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bank_details')
    account_name = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-is_default', '-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.upi_id or self.account_number}"


class OTP(models.Model):
    """OTP verification codes for phone number authentication"""
    phone_number = models.CharField(max_length=15)
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=[
        ('LOGIN', 'Login'),
        ('REGISTRATION', 'Registration'),
        ('PASSWORD_RESET', 'Password Reset'),
        ('SIGNUP', 'Signup'),
    ], default='LOGIN')
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.IntegerField(default=0)  # Track failed verification attempts
    verification_id = models.CharField(max_length=255, blank=True, null=True)  # Message Central verification ID
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone_number', '-created_at']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.otp_code} - {self.purpose}"

    def is_expired(self):
        """Check if OTP is expired"""
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def increment_attempts(self):
        """Increment failed attempts counter"""
        self.attempts += 1
        self.last_attempt_at = timezone.now()
        self.save()

    def can_verify(self):
        """Check if OTP can still be verified (not expired, not used, attempts < 10)"""
        if self.is_used or self.is_expired():
            return False
        
        if self.attempts >= 10:
            # Check if 5 minutes have passed since the last attempt
            if self.last_attempt_at:
                wait_until = self.last_attempt_at + timezone.timedelta(minutes=5)
                if timezone.now() < wait_until:
                    return False
        
        return True


class PendingPayment(models.Model):
    """Track 10% commission from payouts as pending payments"""
    round = models.ForeignKey('game.GameRound', on_delete=models.CASCADE, related_name='pending_payments')
    bet = models.ForeignKey('game.Bet', on_delete=models.CASCADE, related_name='pending_payment')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pending_payments')
    total_payout = models.DecimalField(max_digits=10, decimal_places=2, help_text="Total payout amount (100%)")
    winner_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount paid to winner (90%)")
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Commission amount (10%)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['round']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"Round {self.round.round_id} - {self.user.username} - Commission: ₹{self.commission_amount}"




