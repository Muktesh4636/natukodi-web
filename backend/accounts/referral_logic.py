from decimal import Decimal

def calculate_milestone_bonus(total_referrals):
    """
    Calculate milestone bonus based on number of referrals:
    - 3 referrals: ₹500 bonus
    - 5 referrals: ₹1000 bonus
    - 10 referrals: ₹2500 bonus
    - 20 referrals: ₹5000 bonus
    - 50 referrals: ₹15000 bonus
    - 100 referrals: ₹50000 bonus
    
    Returns the bonus amount for the highest milestone achieved.
    """
    if total_referrals >= 100:
        return Decimal('50000')
    elif total_referrals >= 50:
        return Decimal('15000')
    elif total_referrals >= 20:
        return Decimal('5000')
    elif total_referrals >= 10:
        return Decimal('2500')
    elif total_referrals >= 5:
        return Decimal('1000')
    elif total_referrals >= 3:
        return Decimal('500')
    else:
        return Decimal('0')


def get_next_milestone(total_referrals):
    """Get the next milestone and progress"""
    milestones = [
        (3, Decimal('500')),
        (5, Decimal('1000')),
        (10, Decimal('2500')),
        (20, Decimal('5000')),
        (50, Decimal('15000')),
        (100, Decimal('50000'))
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
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Count total referrals
    total_referrals = User.objects.filter(referred_by=referrer_user).count()
    
    # Get current milestone bonus
    current_bonus = calculate_milestone_bonus(total_referrals)
    
    if current_bonus == 0:
        return False
    
    # Determine which milestone was reached
    milestone_levels = [
        (3, Decimal('500')),
        (5, Decimal('1000')),
        (10, Decimal('2500')),
        (20, Decimal('5000')),
        (50, Decimal('15000')),
        (100, Decimal('50000'))
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
    Calculate referral bonus based on deposit amount:
    - 100 -> 100 bonus
    - 200 -> 10 bonus (Wait, user said 200 -> 10, but then said 200-500 -> 150? Let's re-read)
    - 500 -> 300 bonus
    - 1000 -> 500 bonus
    - 5000 -> 1000 bonus
    
    Rule: if deposit is between two values, use the ceil value bonus.
    Example: 450 is between 200 and 500 -> 150 bonus (Wait, user said 450 -> 150, but 500 is 300? Ceil of 450 is 500)
    Example: 4000 is between 1000 and 5000 -> 500 bonus (Ceil of 4000 is 5000, but user said 500 bonus? 1000 is 500)
    
    Let's re-parse user rules:
    1. 100 -> 100
    2. 200 -> 10 (User might mean 100? or 150? Let's check the logic again)
    3. 500 -> 300
    4. 1000 -> 500
    5. 5000 -> 1000
    
    "if any user deposit between any two amount he will be eligible for ceil value bonous only"
    "if he deposit 450 he will get only 150 bonous beacuse he is in between 200 and 500" -> This contradicts "ceil value". 
    Ceil of 450 is 500. Bonus for 500 is 300. But user says 150.
    Wait, maybe the bonus for 200 is 150?
    "if he deposit 4000 he will get bonous 500 only because he will be in ceil value of 1000" -> This means "floor value" or "previous tier".
    
    Let's re-read carefully:
    "if he deposit 4000 he will get bonous 500 only because he will be in ceil value of 1000"
    "for 1000 to 4999 we will provide only 500 bonous"
    This means:
    [100, 199] -> 100
    [200, 499] -> 150 (Assuming 200 tier is 150 based on the 450 example)
    [500, 999] -> 300
    [1000, 4999] -> 500
    [5000, inf] -> 1000
    
    Wait, user said "if user add 200 he will be getting 10". This might be a typo for 150? 
    "if he deposit 450 he will get only 150 bonous beacuse he is in between 200 and 500"
    Yes, 200 tier bonus is 150.
    
    Final Table:
    Amount >= 5000: 1000
    Amount >= 1000: 500
    Amount >= 500: 300
    Amount >= 200: 150
    Amount >= 100: 100
    """
    amount = Decimal(str(deposit_amount))
    
    if amount >= 5000:
        return Decimal('1000')
    elif amount >= 1000:
        return Decimal('500')
    elif amount >= 500:
        return Decimal('300')
    elif amount >= 200:
        return Decimal('150')
    elif amount >= 100:
        return Decimal('100')
    else:
        return Decimal('0')
