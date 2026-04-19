from django.db import models
from django.conf import settings
from decimal import Decimal
import json
import random


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
    total_amount = models.BigIntegerField(default=0)

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
    chip_amount = models.BigIntegerField()
    payout_amount = models.BigIntegerField(default=0)
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at', 'user_id'], name='bet_leaderboard_created_user'),
        ]
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
    can_view_recent_rounds = models.BooleanField(default=True)
    can_view_all_bets = models.BooleanField(default=True)
    can_view_wallets = models.BooleanField(default=True)
    can_view_players = models.BooleanField(default=True)
    can_view_deposit_requests = models.BooleanField(default=True)
    can_view_withdraw_requests = models.BooleanField(default=True)
    can_view_transactions = models.BooleanField(default=True)
    can_view_game_history = models.BooleanField(default=True)
    can_view_game_settings = models.BooleanField(default=False)  # Super Admin only by default
    can_view_help_center = models.BooleanField(default=False)
    can_view_white_label = models.BooleanField(default=False)
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
            'recent_rounds': self.can_view_recent_rounds,
            'all_bets': self.can_view_all_bets,
            'wallets': self.can_view_wallets,
            'players': self.can_view_players,
            'deposit_requests': self.can_view_deposit_requests,
            'withdraw_requests': self.can_view_withdraw_requests,
            'transactions': self.can_view_transactions,
            'game_history': self.can_view_game_history,
            'game_settings': self.can_view_game_settings,
            'help_center': self.can_view_help_center,
            'white_label': self.can_view_white_label,
            'admin_management': self.can_view_admin_management,
            'payment_methods': self.can_manage_payment_methods,
        }


class UserSoundSetting(models.Model):
    """User-specific sound settings"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sound_settings')
    background_music_volume = models.FloatField(default=0.5)  # 0.0 to 1.0
    is_muted = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sound settings for {self.user.username}"


class MegaSpinProbability(models.Model):
    """Probability configuration for Mega Spin"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mega_spin_probability', null=True, blank=True)
    # If user is null, it's the global default probability
    
    # Probabilities for each slice/number (0-100)
    # Assuming 8 slices for the wheel
    prob_1 = models.FloatField(default=12.5)
    prob_2 = models.FloatField(default=12.5)
    prob_3 = models.FloatField(default=12.5)
    prob_4 = models.FloatField(default=12.5)
    prob_5 = models.FloatField(default=12.5)
    prob_6 = models.FloatField(default=12.5)
    prob_7 = models.FloatField(default=12.5)
    prob_8 = models.FloatField(default=12.5)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Mega Spin Probabilities"

    def __str__(self):
        return f"Mega Spin Prob for {self.user.username if self.user else 'Global Default'}"


class DailyRewardProbability(models.Model):
    """Probability configuration for Daily Reward"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_reward_probability', null=True, blank=True)
    # If user is null, it's the global default probability
    
    # Probabilities for different reward amounts (0-100)
    # Example: 5, 10, 20, 50, 100, 200, 500
    prob_low = models.FloatField(default=70.0)    # Probability for low rewards (e.g., 5-10)
    prob_medium = models.FloatField(default=20.0) # Probability for medium rewards (e.g., 20-50)
    prob_high = models.FloatField(default=9.0)    # Probability for high rewards (e.g., 100-200)
    prob_mega = models.FloatField(default=1.0)    # Probability for mega rewards (e.g., 500)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Daily Reward Probabilities"

    def __str__(self):
        return f"Daily Reward Prob for {self.user.username if self.user else 'Global Default'}"


class LeaderboardSetting(models.Model):
    """Leaderboard prize settings"""
    prize_1st = models.BigIntegerField(default=1000)
    prize_2nd = models.BigIntegerField(default=500)
    prize_3rd = models.BigIntegerField(default=100)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Leaderboard Prizes: 1st: {self.prize_1st}, 2nd: {self.prize_2nd}, 3rd: {self.prize_3rd}"


class WhiteLabelLead(models.Model):
    """Leads/enquiries from white-label page (public form)."""
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=30)
    message = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.phone_number})"


class LeaderboardPayout(models.Model):
    """Tracks daily leaderboard prize payouts to prevent duplicates."""
    period_end = models.DateTimeField(help_text="Leaderboard period end time (UTC).")
    rank = models.IntegerField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leaderboard_payouts')
    amount = models.BigIntegerField()
    transaction_id = models.BigIntegerField(null=True, blank=True)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-awarded_at']
        constraints = [
            models.UniqueConstraint(fields=['period_end', 'rank'], name='uniq_leaderboard_payout_period_rank'),
            models.UniqueConstraint(fields=['period_end', 'user'], name='uniq_leaderboard_payout_period_user'),
        ]

    def __str__(self):
        return f"{self.period_end} rank {self.rank} -> {self.user_id} ({self.amount})"


class UserDailyTurnover(models.Model):
    """
    Cached daily turnover per user for the leaderboard period (23:00–23:00 IST).
    Updated by the bet worker on place_bet/remove_bet; avoids aggregating Bet on every API call.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_turnovers'
    )
    period_date = models.DateField(
        help_text='IST date of the period start (23:00 on this date starts the period).'
    )
    turnover = models.BigIntegerField(default=0, help_text='Sum of chip_amount for this user in this period.')

    class Meta:
        ordering = ['-period_date', '-turnover']
        unique_together = [('user', 'period_date')]
        indexes = [
            models.Index(fields=['period_date', '-turnover'], name='udt_period_turnover'),
        ]
        verbose_name = 'User daily turnover (leaderboard)'
        verbose_name_plural = 'User daily turnovers (leaderboard)'

    def __str__(self):
        return f"{self.user_id} {self.period_date}: {self.turnover}"


# ─────────────────────────────────────────────
#  ADDICTION / RETENTION ENGINE MODELS
# ─────────────────────────────────────────────

DAY_TYPES = [
    ('WIN', 'Win Day'),
    ('LOSS', 'Loss Day'),
    ('BREAK_EVEN', 'Break Even Day'),
    ('BIG_WIN', 'Big Win Day'),
]

PHASE_CHOICES = [
    ('HOOK', 'Hook (Week 1)'),
    ('SLOWDOWN', 'Slow Down (Week 2)'),
    ('LOSSES', 'Losses (Week 3)'),
    ('HARVEST', 'Harvest (Week 4+)'),
]


def _generate_30_day_chart():
    """
    Generate a randomised but controlled 30-day win/loss chart.

    Week 1 (days 0-6):   min 5 WIN days
    Week 2 (days 7-13):  min 3 WIN days, 2 BREAK_EVEN
    Week 3 (days 14-20): max 1 WIN day, 2 BREAK_EVEN
    Week 4+ (days 21-29): LOSS LOSS BIG_WIN pattern (repeating every 3)
    """
    # Week 1
    w1_extras = random.sample(['LOSS', 'BREAK_EVEN'], 2)
    week1 = ['WIN'] * 5 + w1_extras
    random.shuffle(week1)

    # Week 2
    w2_pool = ['LOSS', 'LOSS', 'BREAK_EVEN', 'BREAK_EVEN']
    week2 = ['WIN'] * 3 + w2_pool
    random.shuffle(week2)

    # Week 3
    week3 = ['WIN'] * 1 + ['LOSS'] * 4 + ['BREAK_EVEN'] * 2
    random.shuffle(week3)

    # Week 4+ (9 days: 3 cycles of LOSS LOSS BIG_WIN)
    week4 = ['LOSS', 'LOSS', 'BIG_WIN',
             'LOSS', 'LOSS', 'BIG_WIN',
             'LOSS', 'LOSS', 'BIG_WIN']

    return week1 + week2 + week3 + week4  # 28 days (close enough; repeats after)


# Daily time targets (seconds) — increases every 2 days
_TIME_TARGETS = [
    3600, 3600,          # Day 1-2:   1 hour
    4500, 4500,          # Day 3-4:   1.25 hours
    5400, 5400, 5400,    # Day 5-7:   1.5 hours
    6300, 6300,          # Day 8-9:   1.75 hours
    7200, 7200, 7200,    # Day 10-12: 2 hours
    8100, 8100,          # Day 13-14: 2.25 hours
    9000, 9000, 9000,    # Day 15-17: 2.5 hours
    9900, 9900,          # Day 18-19: 2.75 hours
    10800, 10800,        # Day 20-21: 3 hours
    11700, 11700,        # Day 22-23: 3.25 hours
    12600, 12600, 12600, # Day 24-26: 3.5 hours
    14400, 14400,        # Day 27-28: 4 hours
    16200,               # Day 29:    4.5 hours
    18000,               # Day 30:    5 hours
]


def get_time_target(active_day):
    """Return daily play-time target in seconds for a given active day (1-indexed)."""
    idx = max(0, min(active_day - 1, len(_TIME_TARGETS) - 1))
    return _TIME_TARGETS[idx]


class PlayerJourney(models.Model):
    """
    Stores each player's 30-day chart and active-day counter.
    Created on first deposit.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='journey'
    )
    # JSON list of 30 day-type strings
    chart_json = models.TextField(default='[]')
    # How many days the player has actually played (not calendar days)
    active_days = models.PositiveIntegerField(default=0)
    # Date of last actual play (IST date)
    last_play_date = models.DateField(null=True, blank=True)
    # Calendar date of first deposit
    first_deposit_date = models.DateField(null=True, blank=True)
    # Is account flagged for multi-account abuse?
    is_flagged = models.BooleanField(default=False)
    is_algo_test = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Player Journey'
        verbose_name_plural = 'Player Journeys'

    def __str__(self):
        return f"{self.user.username} — Active Day {self.active_days}"

    @property
    def chart(self):
        try:
            return json.loads(self.chart_json)
        except Exception:
            return []

    @chart.setter
    def chart(self, value):
        self.chart_json = json.dumps(value)

    def get_day_type(self, day_number):
        """Return day type for given 1-indexed active day."""
        chart = self.chart
        if not chart:
            return 'WIN'
        idx = min(day_number - 1, len(chart) - 1)
        # Journey complete after 30 days — pure random
        if day_number - 1 >= len(chart):
            return 'RANDOM'
        return chart[idx]

    def initialise_chart(self):
        """Generate and save a fresh 30-day chart."""
        self.chart = _generate_30_day_chart()
        self.save(update_fields=['chart_json', 'updated_at'])

    def get_phase(self):
        if self.active_days <= 7:
            return 'HOOK'
        elif self.active_days <= 14:
            return 'SLOWDOWN'
        elif self.active_days <= 21:
            return 'LOSSES'
        return 'HARVEST'


class PlayerDailyState(models.Model):
    """
    Per-player per-day state used by the smart dice engine.
    One row per player per IST calendar date.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_states'
    )
    date = models.DateField()
    active_day_number = models.PositiveIntegerField(default=1)
    day_type = models.CharField(max_length=20, choices=DAY_TYPES, default='WIN')

    # Balance management
    deposit_today = models.BigIntegerField(default=0)
    floor_balance = models.BigIntegerField(default=0)
    emergency_floor = models.BigIntegerField(default=0)
    target_min = models.BigIntegerField(default=0)
    target_max = models.BigIntegerField(default=0)

    # Budget
    daily_budget = models.BigIntegerField(default=0)
    budget_used = models.BigIntegerField(default=0)

    # Session time
    time_target_seconds = models.IntegerField(default=3600)
    time_played_seconds = models.IntegerField(default=0)
    time_target_reached = models.BooleanField(default=False)

    # Round tracking
    rounds_today = models.IntegerField(default=0)
    rounds_since_last_win = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'date')]
        ordering = ['-date']
        verbose_name = 'Player Daily State'
        verbose_name_plural = 'Player Daily States'

    def __str__(self):
        return f"{self.user.username} {self.date} — {self.day_type}"

    @property
    def budget_remaining(self):
        return max(0, self.daily_budget - self.budget_used)

    @classmethod
    def compute_floor_and_target(cls, deposit_amount, day_type):
        """
        Given today's deposit and day type, return
        (floor, emergency_floor, target_min, target_max, budget).
        """
        if day_type == 'WIN':
            floor = int(deposit_amount * 0.50)
            emergency = int(deposit_amount * 0.25)
            target_min = int(deposit_amount * 1.50)
            target_max = int(deposit_amount * 2.50)
            low = int(deposit_amount * 1.0)
            high = int(deposit_amount * 2.0)
        elif day_type == 'BIG_WIN':
            floor = int(deposit_amount * 0.30)
            emergency = int(deposit_amount * 0.15)
            target_min = int(deposit_amount * 2.0)
            target_max = int(deposit_amount * 4.0)
            low = int(deposit_amount * 1.5)
            high = int(deposit_amount * 3.0)
        elif day_type == 'BREAK_EVEN':
            floor = int(deposit_amount * 0.40)
            emergency = int(deposit_amount * 0.20)
            target_min = int(deposit_amount * 0.90)
            target_max = int(deposit_amount * 1.10)
            low = 0
            high = 0
        else:  # LOSS
            floor = int(deposit_amount * 0.20)
            emergency = int(deposit_amount * 0.10)
            target_min = 0
            target_max = int(deposit_amount * 0.50)
            low = 0
            high = 0

        budget = random.randint(low, high) if high > low else 0
        return floor, emergency, target_min, target_max, budget


class IPTracker(models.Model):
    """
    Tracks IP addresses and which accounts have used them.
    3rd+ account from same IP is flagged as RANDOM_ONLY.
    """
    ip_address = models.GenericIPAddressField(unique=True)
    # JSON list of user IDs
    account_ids_json = models.TextField(default='[]')
    flagged_ids_json = models.TextField(default='[]')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'IP Tracker'
        verbose_name_plural = 'IP Trackers'

    def __str__(self):
        return f"{self.ip_address} — {len(self.account_ids)} accounts"

    @property
    def account_ids(self):
        try:
            return json.loads(self.account_ids_json)
        except Exception:
            return []

    @property
    def flagged_ids(self):
        try:
            return json.loads(self.flagged_ids_json)
        except Exception:
            return []

    @classmethod
    def register_login(cls, ip_address, user_id):
        """
        Register a login from an IP. Returns True if account is flagged.
        Max 2 accounts per IP allowed before flagging.
        """
        if not ip_address or ip_address in ('127.0.0.1', '::1'):
            return False  # Never flag localhost

        obj, _ = cls.objects.get_or_create(ip_address=ip_address)
        ids = obj.account_ids
        flagged = obj.flagged_ids

        if user_id in ids:
            return user_id in flagged

        ids.append(user_id)
        obj.account_ids_json = json.dumps(ids)

        if len(ids) > 2:
            # 3rd+ account — flag it
            flagged.append(user_id)
            obj.flagged_ids_json = json.dumps(flagged)

        obj.save(update_fields=['account_ids_json', 'flagged_ids_json', 'updated_at'])
        return user_id in flagged


class LiveStream(models.Model):
    """WebRTC live stream session — one active stream at a time."""
    title = models.CharField(max_length=200, default='Live Stream')
    is_live = models.BooleanField(default=False)
    offer_sdp = models.TextField(blank=True, default='')
    answer_sdp = models.TextField(blank=True, default='')
    broadcaster_candidates = models.TextField(blank=True, default='[]')
    viewer_candidates = models.TextField(blank=True, default='[]')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'LiveStream: {self.title} ({"live" if self.is_live else "offline"})'


class CricketBet(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cricket_bets',
    )
    event_id = models.BigIntegerField()
    event_name = models.CharField(max_length=255)
    market_id = models.BigIntegerField()
    market_name = models.CharField(max_length=255)
    outcome_id = models.BigIntegerField()
    outcome_name = models.CharField(max_length=255)
    odds = models.DecimalField(max_digits=10, decimal_places=2)
    stake = models.BigIntegerField(help_text='Stake in paise (smallest currency unit)')
    potential_payout = models.BigIntegerField()
    status = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pending'), ('WON', 'Won'), ('LOST', 'Lost'), ('VOID', 'Void')],
        default='PENDING',
    )
    payout_amount = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Cricket Bet'
        verbose_name_plural = 'Cricket Bets'
        ordering = ['-created_at']

    def __str__(self):
        return f'CricketBet #{self.pk} – {self.user} {self.status}'


class CockFightSession(models.Model):
    status = models.CharField(
        max_length=20,
        choices=[('OPEN', 'Open'), ('SETTLED', 'Settled')],
        default='OPEN',
        db_index=True,
    )
    winner = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'CockFightSession #{self.pk} ({self.status})'


class CockFightBet(models.Model):
    from decimal import Decimal as _D
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cock_fight_bets',
    )
    session = models.ForeignKey(
        CockFightSession,
        on_delete=models.CASCADE,
        related_name='bets',
    )
    side = models.CharField(max_length=10)
    stake = models.BigIntegerField(help_text='Stake in same unit as wallet balance')
    odds = models.DecimalField(max_digits=10, decimal_places=2, default=_D('9.00'))
    potential_payout = models.BigIntegerField(help_text='Total return if win')
    status = models.CharField(
        max_length=20,
        choices=[('PENDING', 'Pending'), ('WON', 'Won'), ('LOST', 'Lost'), ('VOID', 'Void')],
        default='PENDING',
    )
    payout_amount = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['session', 'status'], name='cockfightbet_sess_stat_idx')]

    def __str__(self):
        return f'CockFightBet #{self.pk} – {self.user} {self.side} {self.status}'


class ColourRound(models.Model):
    STATUS_CHOICES = [
        ('BETTING', 'Betting Open'),
        ('CLOSED', 'Betting Closed'),
        ('RESULT', 'Result Announced'),
        ('COMPLETED', 'Completed'),
    ]
    RESULT_CHOICES = [
        ('red', 'Red'),
        ('green', 'Green'),
        ('red_violet', 'Red & Violet'),
        ('green_violet', 'Green & Violet'),
    ]
    round_id = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='BETTING')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, null=True, blank=True)
    number = models.IntegerField(null=True, blank=True, help_text='Result number 0-9')
    start_time = models.DateTimeField(auto_now_add=True)
    close_time = models.DateTimeField(null=True, blank=True)
    result_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Colour Round'
        verbose_name_plural = 'Colour Rounds'
        ordering = ['-start_time']

    def __str__(self):
        return f'ColourRound {self.round_id} ({self.status})'


class ColourBet(models.Model):
    BET_CHOICES = [
        ('red', 'Red'),
        ('green', 'Green'),
        ('violet', 'Violet'),
        ('number', 'Number'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('WON', 'Won'),
        ('LOST', 'Lost'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='colour_bets',
    )
    round = models.ForeignKey(
        ColourRound,
        on_delete=models.CASCADE,
        related_name='bets',
    )
    bet_on = models.CharField(
        max_length=10,
        choices=BET_CHOICES,
        help_text='"red","green","violet" or "number"',
    )
    number = models.IntegerField(null=True, blank=True, help_text='0-9, only when bet_on=number')
    amount = models.BigIntegerField()
    payout = models.BigIntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Colour Bet'
        verbose_name_plural = 'Colour Bets'
        ordering = ['-created_at']

    def __str__(self):
        return f'ColourBet #{self.pk} – {self.user} {self.bet_on} {self.status}'
