import logging
import decimal
from decimal import Decimal

def calculate_milestone_bonus(total_referrals):
    """
    Calculate milestone bonus based on number of referrals.
    """
    if total_referrals >= 100:
        return decimal.Decimal('50000')
    elif total_referrals >= 50:
        return decimal.Decimal('15000')
    elif total_referrals >= 20:
        return decimal.Decimal('5000')
    elif total_referrals >= 10:
        return decimal.Decimal('2500')
    elif total_referrals >= 5:
        return decimal.Decimal('1000')
    elif total_referrals >= 3:
        return decimal.Decimal('500')
    else:
        return decimal.Decimal('0')


def get_next_milestone(total_referrals):
    """Get the next milestone and progress"""
    milestones = [
        (3, decimal.Decimal('500')),
        (5, decimal.Decimal('1000')),
        (10, decimal.Decimal('2500')),
        (20, decimal.Decimal('5000')),
        (50, decimal.Decimal('15000')),
        (100, decimal.Decimal('50000'))
    ]
    
    for milestone_count, bonus in milestones:
        if total_referrals < milestone_count:
            progress_pct = min((total_referrals / milestone_count * 100), 100.0)
            return {
                'next_milestone': milestone_count,
                'next_bonus': float(bonus),
                'current_progress': total_referrals,
                'progress_percentage': progress_pct
            }
    
    return {
        'next_milestone': None,
        'next_bonus': 0,
        'current_progress': total_referrals,
        'progress_percentage': 100.0
    }


def check_and_award_milestone_bonus(referrer_user):
    """
    Check if referrer has reached a new milestone and award bonus if needed.
    Returns True if a milestone bonus was awarded, False otherwise.
    
    Note: This awards the highest milestone bonus achieved, but only once per milestone level.
    """
    from django.db.models import Count
    from .models import User, Wallet, Transaction
    
    logger = logging.getLogger(__name__)
    
    # Count total referrals
    total_referrals = User.objects.filter(referred_by=referrer_user).count()
    
    # Get current milestone bonus
    current_bonus = calculate_milestone_bonus(total_referrals)
    
    if current_bonus == 0:
        return False
    
    # Determine which milestone was reached
    milestone_levels = [
        (3, decimal.Decimal('500')),
        (5, decimal.Decimal('1000')),
        (10, decimal.Decimal('2500')),
        (20, decimal.Decimal('5000')),
        (50, decimal.Decimal('15000')),
        (100, decimal.Decimal('50000'))
    ]
    
    # Find the highest milestone reached
    reached_milestone = None
    for milestone_count, bonus_amount in milestone_levels:
        if total_referrals >= milestone_count and current_bonus == bonus_amount:
            reached_milestone = milestone_count
            break
    
    if reached_milestone is None:
        return False
    
    # Check if user has already received this specific milestone bonus
    milestone_transactions = Transaction.objects.filter(
        user=referrer_user,
        transaction_type='MILESTONE_BONUS',
        description__icontains=f"{reached_milestone} referrals"
    )
    
    # If milestone bonus already awarded for this level, skip
    if milestone_transactions.exists():
        return False
    
    # Award milestone bonus
    try:
        wallet, _ = Wallet.objects.get_or_create(user=referrer_user)
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        
        balance_before = wallet.balance
        wallet.balance += current_bonus
        wallet.save()
        
        balance_after = wallet.balance
        
        # Create transaction record
        Transaction.objects.create(
            user=referrer_user,
            transaction_type='MILESTONE_BONUS',
            amount=current_bonus,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"Milestone bonus: ₹{current_bonus} for {reached_milestone} referrals"
        )
        
        logger.info(f"Milestone bonus of ₹{current_bonus} awarded to {referrer_user.username} for {reached_milestone} referrals")
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
