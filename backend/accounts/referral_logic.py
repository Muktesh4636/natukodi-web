import logging
import decimal
import random
from decimal import Decimal

# Tiered milestone: 3 refs (with deposit) → ₹500, 5 more → ₹1000, then cycle resets
# Only referrals who complete first deposit count
TIER_1_COUNT = 3
TIER_1_BONUS = Decimal('500')
TIER_2_COUNT = 5  # additional after tier 1
TIER_2_BONUS = Decimal('1000')
CYCLE_SIZE = TIER_1_COUNT + TIER_2_COUNT  # 8


def get_tier_progress(active_referrals):
    """
    Get current tier and progress. active_referrals = referrals who completed first deposit.
    Returns: (tier, current, target, bonus) where tier is 1 or 2, current/target for display (e.g. 1/3, 2/5)
    """
    progress_in_cycle = active_referrals % CYCLE_SIZE
    if progress_in_cycle < TIER_1_COUNT:
        return (1, progress_in_cycle, TIER_1_COUNT, TIER_1_BONUS)
    else:
        return (2, progress_in_cycle - TIER_1_COUNT, TIER_2_COUNT, TIER_2_BONUS)


def calculate_milestone_bonus(active_referrals):
    """
    Calculate milestone bonus for current tier completion.
    Tier 1: 3 refs with deposit → ₹500
    Tier 2: 5 more refs (8 total) → ₹1000
    Then cycle resets.
    """
    progress_in_cycle = active_referrals % CYCLE_SIZE
    if progress_in_cycle == TIER_1_COUNT - 1 and active_referrals > 0:
        return TIER_1_BONUS
    if progress_in_cycle == CYCLE_SIZE - 1 and active_referrals > 0:
        return TIER_2_BONUS
    return Decimal('0')


def get_next_milestone(active_referrals):
    """Get the next milestone and progress for display"""
    tier, current, target, bonus = get_tier_progress(active_referrals)
    progress_pct = (current / target * 100) if target > 0 else 0
    return {
        'tier': tier,
        'current_progress': current,
        'target': target,
        'next_milestone': target,
        'next_bonus': float(bonus),
        'next_bonus_display': None,
        'progress_percentage': min(progress_pct, 100.0)
    }


def check_and_award_milestone_bonus(referrer_user, active_referrals):
    """
    Check if referrer has reached a new milestone and award bonus if needed.
    Only call when a referral completes their FIRST deposit (active_referrals just increased).
    Returns True if a milestone bonus was awarded, False otherwise.
    
    Tier 1: 3 refs with deposit → ₹500
    Tier 2: 8 refs total (5 more) → ₹1000, then cycle resets.
    """
    from .models import User, Wallet, Transaction

    logger = logging.getLogger(__name__)

    # Award only at exact milestone counts: 3, 8, 11, 16, ...
    progress_in_cycle = active_referrals % CYCLE_SIZE
    if progress_in_cycle == 0 and active_referrals > 0:
        # Just completed tier 2 (8, 16, 24, ...) → ₹1000
        current_bonus = TIER_2_BONUS
        milestone_desc = "5 referrals (first deposit)"
    elif progress_in_cycle == TIER_1_COUNT:
        # Just completed tier 1 (3, 11, 19, ...) → ₹500
        current_bonus = TIER_1_BONUS
        milestone_desc = "3 referrals (first deposit)"
    else:
        return False

    # Check if we already awarded for this exact count (avoid double-award)
    desc_pattern = f"({active_referrals} total)"
    if Transaction.objects.filter(
        user=referrer_user,
        transaction_type='MILESTONE_BONUS',
        description__icontains=desc_pattern
    ).exists():
        return False

    try:
        wallet, _ = Wallet.objects.get_or_create(user=referrer_user)
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)

        balance_before = wallet.balance
        wallet.balance += current_bonus
        wallet.save()

        balance_after = wallet.balance

        Transaction.objects.create(
            user=referrer_user,
            transaction_type='MILESTONE_BONUS',
            amount=current_bonus,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"Milestone bonus: ₹{current_bonus} for {milestone_desc} ({active_referrals} total)"
        )

        logger.info(f"Milestone bonus of ₹{current_bonus} awarded to {referrer_user.username} for {active_referrals} referrals (first deposit)")
        return True
    except Exception as e:
        logger.error(f"Failed to award milestone bonus to {referrer_user.username}: {str(e)}")
        return False


def calculate_referral_bonus(deposit_amount):
    """
    Calculate referral bonus based on deposit amount.
    If deposit is ₹100 or more, referrer gets ₹100 bonus.
    """
    amount = decimal.Decimal(str(deposit_amount))
    
    if amount >= 100:
        return decimal.Decimal('100')
    else:
        return decimal.Decimal('0')
