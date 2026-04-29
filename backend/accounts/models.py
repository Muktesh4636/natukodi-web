import re
import secrets

from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone


REFERRAL_CODE_MAX_LEN = 20


def referral_identity_slug(username, phone_number):
    """
    Base slug for referral codes: username (letters/digits only, lowercased), else phone digits,
    else empty string.
    """
    raw = (username or '').strip().lower()
    slug = re.sub(r'[^a-z0-9]', '', raw)
    if len(slug) >= 2:
        return slug[:REFERRAL_CODE_MAX_LEN]
    if slug:
        return slug[:REFERRAL_CODE_MAX_LEN]
    digits = re.sub(r'\D', '', str(phone_number or ''))
    if digits:
        return digits[-REFERRAL_CODE_MAX_LEN:]
    return ''


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
        limit_choices_to={'is_staff': True},
        help_text='For players: the franchise admin (or Super Admin) this user is under. Deposit/withdraw requests show to that admin.',
    )
    # For staff users (workers): the admin whose queue this worker sees. If set, this user sees deposit/withdraw requests of that admin.
    works_under = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_workers',
        limit_choices_to={'is_staff': True},
        help_text='For workers: the admin under whom this worker is assigned. This worker will see that admin\'s deposit/withdraw requests.',
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
    # Cached count of how many users this user has referred (kept in sync via save/delete)
    total_referrals_count = models.PositiveIntegerField(default=0, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    # When True, user appears only in Franchise Balance (franchise owners list), not in Worker Management
    is_franchise_only = models.BooleanField(default=False)

    def __str__(self):
        return self.username
    
    def generate_unique_referral_code(self):
        """
        Unique code derived from username (e.g. ``ravi``, ``ravi2``) or phone digits if username
        has no usable slug; otherwise a short ``ref`` + hex fallback.
        """
        base = referral_identity_slug(self.username, self.phone_number)
        if not base:
            base = 'ref' + secrets.token_hex(3)

        base = base.lower()[:REFERRAL_CODE_MAX_LEN]

        def _exists(candidate):
            return (
                User.objects.filter(referral_code__iexact=candidate)
                .exclude(pk=self.pk)
                .exists()
            )

        if not _exists(base):
            return base

        for n in range(2, 10_000):
            suffix = str(n)
            head_len = REFERRAL_CODE_MAX_LEN - len(suffix)
            if head_len < 1:
                head_len = 1
            candidate = (base[:head_len] + suffix).lower()[:REFERRAL_CODE_MAX_LEN]
            if not _exists(candidate):
                return candidate

        return (base[:12] + secrets.token_hex(4))[:REFERRAL_CODE_MAX_LEN].lower()
    
    def save(self, *args, **kwargs):
        # Track previous referred_by so we can update referrers' total_referrals_count
        old_referred_by_id = None
        if self.pk:
            old = User.objects.filter(pk=self.pk).values_list('referred_by_id', flat=True).first()
            old_referred_by_id = old

        # Ensure referral code is generated if missing.
        # When instance has pk (existing row), check DB first: request.user from
        # CachedJWTAuthentication is a minimal user (no referral_code) and must
        # not overwrite the real referral_code in DB with a new one.
        if not self.referral_code:
            if self.pk:
                existing = User.objects.filter(pk=self.pk).values_list('referral_code', flat=True).first()
                if existing:
                    self.referral_code = existing
                else:
                    self.referral_code = self.generate_unique_referral_code()
            else:
                self.referral_code = self.generate_unique_referral_code()
        super().save(*args, **kwargs)

        # Keep referrers' total_referrals_count in sync
        new_referred_by_id = self.referred_by_id
        if new_referred_by_id != old_referred_by_id:
            if old_referred_by_id:
                User.objects.filter(pk=old_referred_by_id).update(
                    total_referrals_count=Greatest(F('total_referrals_count') - 1, Value(0))
                )
            if new_referred_by_id:
                User.objects.filter(pk=new_referred_by_id).update(
                    total_referrals_count=F('total_referrals_count') + 1
                )

    def delete(self, *args, **kwargs):
        referrer_id = self.referred_by_id
        super().delete(*args, **kwargs)
        if referrer_id:
            User.objects.filter(pk=referrer_id).update(
                total_referrals_count=Greatest(F('total_referrals_count') - 1, Value(0))
            )


class Wallet(models.Model):
    """User wallet for managing balance"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.BigIntegerField(default=0)
    unavaliable_balance = models.BigIntegerField(default=0, help_text="Amount currently locked or unavaliable for withdrawal")
    turnover = models.BigIntegerField(default=0, help_text="Total amount wagered. Unavailable = max(0, total_deposits - turnover).")
    total_deposits = models.BigIntegerField(default=0, help_text="Cumulative deposits (and bonuses) credited. Unavailable = max(0, total_deposits - turnover).")
    total_deposits_at_last_withdraw = models.BigIntegerField(default=0, help_text="Snapshot of total_deposits when last withdrawal was approved. Unavailable = max(0, (total_deposits - this) - (turnover - turnover_at_last_withdraw)).")
    turnover_at_last_withdraw = models.BigIntegerField(default=0, help_text="Snapshot of turnover when last withdrawal was approved.")
    deposit_rotation_lock = models.BigIntegerField(
        default=0,
        help_text="Amount (deposits/bonuses) still requiring 1x turnover since baseline; see apply_deposit_rotation_credit.",
    )
    deposit_rotation_baseline_turnover = models.BigIntegerField(
        default=0,
        help_text="Turnover snapshot: unavailable lock decreases by (turnover - baseline).",
    )
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
        """
        Deduct amount from wallet (bet placed).

        IMPORTANT: Withdrawable/Unavailable is derived from turnover:
        - unavailable = max(0, balance - turnover)
        - withdrawable = min(balance, turnover)
        So this method only updates balance; turnover is maintained by the bet worker.
        """
        if self.balance >= amount:
            self.balance -= amount
            self.save(update_fields=['balance', 'updated_at'])
            return True
        return False

    def add(self, amount, is_bonus=False):
        """
        Add amount to wallet.

        IMPORTANT: We no longer maintain unavaliable_balance as a stored lock.
        Locking/unlocking is derived from turnover.
        `is_bonus` is kept for backward compatibility but does not change wallet fields.
        """
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])
        return True

    @classmethod
    def apply_deposit_rotation_credit(cls, wallet_pk, amount_int):
        """
        After balance/total_deposits increased by a deposit or bonus credit:
        - Consume any existing lock with turnover since baseline.
        - Add `amount_int` to the rotation lock (needs 1x new turnover from current T).
        So a user with turnover 2000 who deposits 100 gets lock=100 at baseline T=2000 → unavailable 100.
        """
        amount_int = int(amount_int)
        if amount_int <= 0:
            return
        from django.db import connection, transaction

        def _do():
            w = cls.objects.select_for_update().get(pk=wallet_pk)
            T = int(w.turnover or 0)
            lock = int(w.deposit_rotation_lock or 0)
            b = int(w.deposit_rotation_baseline_turnover or 0)
            if lock > 0:
                progress = T - b
                if progress >= lock:
                    lock = 0
                    b = T
                else:
                    lock = lock - progress
                    b = T
            else:
                b = T
            lock += amount_int
            cls.objects.filter(pk=wallet_pk).update(
                deposit_rotation_lock=lock,
                deposit_rotation_baseline_turnover=b,
            )

        if connection.in_atomic_block:
            _do()
        else:
            with transaction.atomic():
                _do()

    @property
    def withdrawable_balance(self):
        """Withdrawable = balance - unavailable; unavailable = max(0, total_deposits - turnover). So user can withdraw winnings + released deposit."""
        try:
            bal = Decimal(str(self.balance))
            unav = self.computed_unavailable_balance
            return max(Decimal('0.00'), bal - unav)
        except Exception:
            return Decimal('0.00')

    @property
    def computed_unavailable_balance(self):
        """Unavailable = deposit_rotation_lock minus turnover since baseline (1x playthrough per credit)."""
        try:
            lock = int(getattr(self, 'deposit_rotation_lock', 0) or 0)
            b = int(getattr(self, 'deposit_rotation_baseline_turnover', 0) or 0)
            T = int(self.turnover or 0)
            remaining = lock - max(0, T - b)
            return max(Decimal('0.00'), Decimal(str(max(0, remaining))))
        except Exception:
            return Decimal('0.00')


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
        ('REFERRAL_COMMISSION', 'Referral Commission'),
        ('MILESTONE_BONUS', 'Milestone Bonus'),
        ('LEADERBOARD_PRIZE', 'Leaderboard Prize'),
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


class ReferralDailyCommission(models.Model):
    """Ledger row + audit for daily referee wallet-loss × referrer slab commission."""

    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_commission_earnings')
    referee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_commission_generated')
    commission_date = models.DateField(db_index=True)
    opening_balance = models.BigIntegerField()
    closing_balance = models.BigIntegerField()
    loss_amount = models.BigIntegerField()
    commission_rate = models.DecimalField(max_digits=7, decimal_places=4)
    commission_amount = models.BigIntegerField()
    transaction = models.OneToOneField(
        Transaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='referral_daily_commission_detail',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('referee', 'commission_date'),
                name='uniq_referral_daily_comm_referee_date',
            ),
        ]
        ordering = ('-commission_date', '-id')

    def __str__(self):
        return (
            f'referrer={self.referrer_id} referee={self.referee_id} '
            f'{self.commission_date} ₹{self.commission_amount}'
        )


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


def normalize_deposit_utr(utr):
    return (utr or '').strip()


def deposit_payment_reference_in_use(utr, exclude_pk=None):
    """
    True if this UTR is already stored on another PENDING or APPROVED deposit.
    Case-insensitive; empty UTR never conflicts. REJECTED rows do not block reuse.
    """
    norm = normalize_deposit_utr(utr)
    if not norm:
        return False
    qs = DepositRequest.objects.filter(
        status__in=['PENDING', 'APPROVED'],
    ).exclude(payment_reference='').filter(payment_reference__iexact=norm)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


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
    # null = global (super admin); set = franchise owner's own payment methods
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='owned_payment_methods')

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


class DeviceToken(models.Model):
    """FCM/APNs token for push notifications"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_tokens')
    fcm_token = models.CharField(max_length=500)
    platform = models.CharField(max_length=20, default='android')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['user', 'fcm_token']]
        indexes = [models.Index(fields=['user']), models.Index(fields=['fcm_token'])]

    def __str__(self):
        return f"{self.user.username} - {self.platform}"


class FranchiseBalance(models.Model):
    """Per-admin franchise balance (float). Deducted on deposit approval, added on withdraw approval."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='franchise_balance',
    )
    franchise_name = models.CharField(
        max_length=120,
        blank=True,
        help_text='Franchise / owner display name (e.g. Muktesh)',
    )
    balance = models.BigIntegerField(default=0, help_text='Balance in same unit as Wallet (e.g. rupees)')
    updated_at = models.DateTimeField(auto_now=True)
    # Per-franchise APK: package name shown in that APK's Help Center (e.g. com.franchise1.app)
    package_name = models.CharField(
        max_length=255,
        blank=True,
        unique=True,
        null=True,
        help_text='APK package name for this franchise; Help Center API returns this franchise\'s numbers when app sends this package.',
    )
    help_whatsapp_number = models.CharField(
        max_length=30,
        blank=True,
        help_text='Help Center WhatsApp number for this franchise\'s APK (e.g. +919876543210).',
    )
    help_telegram = models.CharField(
        max_length=30,
        blank=True,
        help_text='Help Center Telegram number/username for this franchise\'s APK.',
    )
    help_facebook = models.CharField(
        max_length=500,
        blank=True,
        help_text="Help Center Facebook page or profile URL for this franchise's APK.",
    )
    help_instagram = models.CharField(
        max_length=500,
        blank=True,
        help_text="Help Center Instagram profile URL or handle for this franchise's APK.",
    )
    help_youtube = models.CharField(
        max_length=500,
        blank=True,
        help_text="Help Center YouTube channel URL for this franchise's APK.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(balance__gte=0), name='franchise_balance_non_negative'),
        ]
        verbose_name = 'Franchise balance'
        verbose_name_plural = 'Franchise balances'

    def __str__(self):
        name = self.franchise_name or self.user.username
        return f"{name} - ₹{self.balance}"


class FranchiseBalanceLog(models.Model):
    """Log of every add/set balance action by super admin for a franchise."""
    ACTION_ADD = 'ADD'
    ACTION_SET = 'SET'
    ACTION_CHOICES = [
        (ACTION_ADD, 'Add'),
        (ACTION_SET, 'Set'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='franchise_balance_logs',
        help_text='Franchise admin who received the balance',
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    amount = models.BigIntegerField(help_text='For Add: amount added. For Set: new balance value.')
    balance_after = models.BigIntegerField(null=True, blank=True, help_text='Balance after this action')
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='franchise_balance_actions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Franchise balance log'
        verbose_name_plural = 'Franchise balance logs'

    def __str__(self):
        return f"{self.user.username} {self.get_action_display()} ₹{self.amount} at {self.created_at}"


