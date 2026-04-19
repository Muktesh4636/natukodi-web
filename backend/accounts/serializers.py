from django.conf import settings
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.core.validators import MinLengthValidator
from decimal import Decimal
from .models import User, Wallet, Transaction, DepositRequest, WithdrawRequest, PaymentMethod, UserBankDetail, DailyReward


class UserRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[MinLengthValidator(4, message="Password must be at least 4 characters long.")]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2', 'phone_number', 'referral_code')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        # Validate referral code format if provided (case-insensitive match)
        referral_code = attrs.get('referral_code')
        if referral_code:
            referral_code = referral_code.strip()
            # Check if referral code exists and is valid
            if not User.objects.filter(referral_code__iexact=referral_code).exists():
                raise serializers.ValidationError({
                    "referral_code": "Invalid referral code. Please check and try again."
                })
            # Store the actual DB value for create()
            referrer = User.objects.filter(referral_code__iexact=referral_code).first()
            attrs['referral_code'] = referrer.referral_code if referrer else referral_code
        
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        referral_code = validated_data.pop('referral_code', None)
        
        user = User.objects.create_user(**validated_data)
        
        # Handle referral - ensure referral code is valid and not tied to worker
        if referral_code:
            try:
                referrer = User.objects.get(referral_code=referral_code)
                # Ensure referrer is not a worker/professional (referral is independent of worker system)
                # Only set referred_by if referrer exists and has a valid referral code
                if referrer.referral_code:
                    user.referred_by = referrer
                    user.save()
            except User.DoesNotExist:
                # Invalid referral code - user can still register but won't be referred
                pass
        
        # Generate unique referral code (independent of worker/professional system)
        # The save() method will automatically generate a unique code if missing
        if not user.referral_code:
            user.referral_code = user.generate_unique_referral_code()
        user.save()

        # Wallet is automatically created by signal (accounts.signals.create_user_wallet)
        # Using get_or_create as a safety measure in case signal doesn't fire
        Wallet.objects.get_or_create(user=user, defaults={'balance': Decimal('0.00')})
        return user


class UserSerializer(serializers.ModelSerializer):
    is_staff = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'phone_number', 'gender', 'is_staff')
        read_only_fields = ('id', 'is_staff')


class WalletSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    withdrawable_balance = serializers.SerializerMethodField()
    unavaliable_balance = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ('id', 'user', 'balance', 'unavaliable_balance', 'withdrawable_balance', 'created_at', 'updated_at')
        read_only_fields = ('id', 'balance', 'unavaliable_balance', 'withdrawable_balance', 'created_at', 'updated_at')

    def get_withdrawable_balance(self, obj):
        # withdrawable = min(balance, turnover)
        try:
            return str(obj.withdrawable_balance)
        except Exception:
            return "0.00"

    def get_unavaliable_balance(self, obj):
        # unavailable = max(0, balance - turnover)
        try:
            return str(obj.computed_unavailable_balance)
        except Exception:
            return "0.00"


class TransactionSerializer(serializers.ModelSerializer):
    """
    Human-readable ``status`` for clients:

    - ``WIN`` → ``win``
    - ``BET`` → ``bet`` (open stake) or ``loss`` once the round is settled and this bet lost
    - ``DEPOSIT`` → ``successful`` (ledger rows are created after completed deposits; pending is on deposit-requests APIs)
    - ``REFERRAL_BONUS``, ``MILESTONE_BONUS``, ``LEADERBOARD_PRIZE``, ``WITHDRAW``, ``REFUND`` → ``successful``
    """

    status = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = (
            'id',
            'transaction_type',
            'status',
            'amount',
            'balance_before',
            'balance_after',
            'description',
            'created_at',
        )
        read_only_fields = ('id', 'status', 'created_at')

    def _resolve_bet_for_transaction(self, obj):
        """Match a BET ledger row to ``game.Bet`` via ``Bet on N in round <id>`` description."""
        import re

        if obj.transaction_type != 'BET':
            return None
        desc = obj.description or ''
        m = re.search(r'Bet on (\d+) in round (\S+)', desc)
        if not m:
            return None
        number = int(m.group(1))
        round_id = m.group(2).strip()
        try:
            from game.models import Bet

            return (
                Bet.objects.select_related('round')
                .filter(
                    user_id=obj.user_id,
                    round__round_id=round_id,
                    number=number,
                    chip_amount=obj.amount,
                )
                .order_by('-created_at')
                .first()
            )
        except Exception:
            return None

    @staticmethod
    def _round_is_settled(round_obj):
        if round_obj.status in ('RESULT', 'COMPLETED'):
            return True
        dr = round_obj.dice_result
        return dr not in (None, '',)

    def get_status(self, obj):
        t = obj.transaction_type
        if t == 'WIN':
            return 'win'
        if t == 'BET':
            bet = self._resolve_bet_for_transaction(obj)
            if bet is not None and self._round_is_settled(bet.round):
                if not bet.is_winner:
                    return 'loss'
            return 'bet'
        if t == 'DEPOSIT':
            return 'successful'
        if t in ('WITHDRAW', 'REFUND', 'REFERRAL_BONUS', 'MILESTONE_BONUS', 'LEADERBOARD_PRIZE'):
            return 'successful'
        return 'successful'


class DepositRequestSerializer(serializers.ModelSerializer):
    screenshot_url = serializers.SerializerMethodField()
    user = UserSerializer(read_only=True)

    class Meta:
        model = DepositRequest
        fields = (
            'id',
            'user',
            'amount',
            'status',
            'screenshot_url',
            'payment_method',
            'admin_note',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'status', 'created_at', 'updated_at', 'user', 'screenshot_url')

    def get_screenshot_url(self, obj):
        request = self.context.get('request')
        if obj.screenshot and hasattr(obj.screenshot, 'url'):
            if request:
                return request.build_absolute_uri(obj.screenshot.url)
            return obj.screenshot.url
        return None


class DepositRequestMineSerializer(serializers.ModelSerializer):
    """Deposit rows for GET /api/auth/deposits/mine/ — no nested user (caller is authenticated)."""

    class Meta:
        model = DepositRequest
        fields = (
            'id',
            'amount',
            'status',
            'payment_method',
            'admin_note',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class DepositRequestAdminSerializer(DepositRequestSerializer):
    class Meta(DepositRequestSerializer.Meta):
        fields = DepositRequestSerializer.Meta.fields + ('admin_note',)


class WithdrawRequestSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    processed_by_name = serializers.ReadOnlyField(source='processed_by.username')

    class Meta:
        model = WithdrawRequest
        fields = (
            'id',
            'user',
            'amount',
            'status',
            'withdrawal_method',
            'withdrawal_details',
            'admin_note',
            'processed_by_name',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'status', 'created_at', 'updated_at', 'user', 'processed_by_name')


class WithdrawRequestAppSerializer(serializers.ModelSerializer):
    """Minimal withdraw payload for mobile clients (no nested ``user``)."""

    class Meta:
        model = WithdrawRequest
        fields = (
            'id',
            'amount',
            'status',
            'withdrawal_method',
            'withdrawal_details',
            'admin_note',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'amount',
            'status',
            'withdrawal_method',
            'withdrawal_details',
            'admin_note',
            'created_at',
            'updated_at',
        )


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = '__all__'


class UserBankDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserBankDetail
        fields = '__all__'
        read_only_fields = ('id', 'user', 'created_at', 'updated_at')


class DailyRewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReward
        fields = ('id', 'reward_amount', 'reward_type', 'claimed_at', 'reward_date')
        read_only_fields = ('id', 'user', 'claimed_at', 'reward_date')


class DailyRewardHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReward
        fields = ('reward_amount', 'reward_type', 'claimed_at', 'reward_date')




