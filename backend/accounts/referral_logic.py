from decimal import Decimal

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
