# 🎲 Gundu Ata Betting Settlement Process

This document details the **technical implementation** of how betting amounts are settled in Gundu Ata, including the processing of lost bets, won bets, payout calculations, and system integrity measures.

---

## 📊 Settlement Overview

**Betting Settlement** occurs automatically when dice results are announced (51 seconds into each round). The system processes all bets simultaneously and updates wallets in real-time.

### **Settlement Flow:**
```
Round Timer → 51s → Dice Results Announced → Settlement Process → Wallet Updates → Transaction Records
```

---

## ⏱️ Settlement Timing

### **Round Timeline:**
- **0-30s**: Betting open - Users can place/remove bets
- **30-51s**: Betting closed - No more bets allowed, system prepares results
- **51s**: **SETTLEMENT TRIGGER** - Dice results announced, payouts calculated
- **52-80s**: Results displayed, new round begins

### **Settlement Triggers:**
1. **Automatic**: Timer reaches 51 seconds
2. **Manual**: Admin sets dice results (for testing/emergency)
3. **System Recovery**: Re-processing after system restart

---

## 🔍 Bet Classification & Processing

### **1. Bet Status Determination**

Each bet in the round is evaluated against the final dice results:

```python
# Winning Criteria: Number appears 2+ times
winning_numbers = [num for num, count in dice_counts.items() if count >= 2]

# For each bet:
if bet.number in winning_numbers:
    bet.is_winner = True
    bet.payout_amount = bet.chip_amount * frequency_of_number
else:
    bet.is_winner = False
    bet.payout_amount = 0.00  # No payout for losers
```

### **2. Multiplier Calculation**

| Dice Frequency | Multiplier | Formula |
|---------------|------------|---------|
| 2 Times | 2x | `bet_amount * 2` |
| 3 Times | 3x | `bet_amount * 3` |
| 4 Times | 4x | `bet_amount * 4` |
| 5 Times | 5x | `bet_amount * 5` |
| 6 Times | 6x | `bet_amount * 6` |

---

## 💰 Settlement Processing Logic

### **Core Settlement Function**

```python
def calculate_payouts(round_obj, dice_result=None, dice_values=None):
    """
    Process all bets for a round and update wallets
    """
    # Get dice frequency counts
    counts = get_dice_frequency_counts(dice_values)

    # Find winning numbers (appear 2+ times)
    winning_numbers = [num for num, count in counts.items() if count >= 2]

    if not winning_numbers:
        # No winners - all bets are losses
        mark_all_bets_as_losses(round_obj)
        return

    # Process each winning number
    for winning_number in winning_numbers:
        frequency = counts[winning_number]
        payout_multiplier = Decimal(str(frequency))

        # Get all bets on this number
        winning_bets = Bet.objects.filter(round=round_obj, number=winning_number)

        for bet in winning_bets:
            process_winning_bet(bet, payout_multiplier, frequency, round_obj)
```

### **Winning Bet Processing**

```python
def process_winning_bet(bet, multiplier, frequency, round_obj):
    """
    Process a single winning bet
    """
    # Calculate payout: bet_amount * frequency
    total_payout = bet.chip_amount * multiplier

    # Update bet record
    bet.payout_amount = total_payout
    bet.is_winner = True
    bet.save()

    # Credit winner's wallet (100% payout - no commission)
    wallet = bet.user.wallet
    balance_before = wallet.balance
    wallet.add(total_payout)
    balance_after = wallet.balance

    # Create WIN transaction record
    Transaction.objects.create(
        user=bet.user,
        transaction_type='WIN',
        amount=total_payout,
        balance_before=balance_before,
        balance_after=balance_after,
        description=f"Win on number {bet.number} (appeared {frequency}x) in round {round_obj.round_id}"
    )

    logger.info(f"Processed win: {bet.user.username} won ₹{total_payout} on number {bet.number}")
```

### **Losing Bet Processing**

```python
def process_losing_bet(bet, round_obj):
    """
    Process a single losing bet
    """
    # Update bet record (payout_amount remains 0.00)
    bet.is_winner = False
    bet.payout_amount = Decimal('0.00')
    bet.save()

    # NO wallet changes - money stays in system
    # NO transaction record created for losses

    logger.info(f"Processed loss: {bet.user.username} lost ₹{bet.chip_amount} on number {bet.number}")
```

---

## 🏦 Wallet Management During Settlement

### **Wallet Operations**

#### **For Winning Bets:**
```python
# Atomic wallet update
with transaction.atomic():
    balance_before = wallet.balance
    wallet.add(total_payout)  # Add winnings
    balance_after = wallet.balance
```

#### **For Losing Bets:**
```python
# NO wallet changes - money remains in system
# Bet amount was already deducted when bet was placed
```

### **Balance Validation**

```python
def validate_wallet_balance(wallet, required_amount):
    """
    Ensure sufficient balance before operations
    """
    return wallet.balance >= required_amount
```

---

## 📊 Database Transaction Integrity

### **Atomic Operations**

All settlement operations use database transactions to ensure data integrity:

```python
@transaction.atomic
def process_round_settlement(round_obj, dice_values):
    """
    Atomic settlement - either all succeed or all fail
    """
    try:
        # 1. Calculate payouts
        calculate_payouts(round_obj, dice_values=dice_values)

        # 2. Update round status
        round_obj.status = 'RESULT'
        round_obj.result_time = timezone.now()
        round_obj.save()

        # 3. Log settlement completion
        logger.info(f"Settlement completed for round {round_obj.round_id}")

    except Exception as e:
        # Rollback all changes if any step fails
        logger.error(f"Settlement failed for round {round_obj.round_id}: {e}")
        raise
```

### **Data Consistency Checks**

```python
def validate_settlement_integrity(round_obj):
    """
    Post-settlement validation
    """
    total_bets = Bet.objects.filter(round=round_obj).aggregate(
        total_bet_amount=Sum('chip_amount'),
        total_payout_amount=Sum('payout_amount')
    )

    # System should never lose money
    assert total_payout_amount <= total_bet_amount, "Payout exceeds bets!"

    return True
```

---

## 🔄 Bet Lifecycle

### **1. Bet Creation (0-30s)**
```python
# User places bet
bet = Bet.objects.create(
    user=request.user,
    round=current_round,
    number=chosen_number,
    chip_amount=bet_amount
)

# Deduct from wallet immediately
wallet.deduct(bet_amount)

# Create BET transaction
Transaction.objects.create(
    user=user,
    transaction_type='BET',
    amount=-bet_amount,  # Negative for debit
    description=f"Bet on number {number} in round {round_id}"
)
```

### **2. Bet Removal (0-30s)**
```python
# User removes bet before closure
wallet.add(bet.chip_amount)  # Refund

# Create REFUND transaction
Transaction.objects.create(
    user=user,
    transaction_type='REFUND',
    amount=bet.chip_amount,  # Positive for credit
    description=f"Refund bet on number {number} in round {round_id}"
)

# Delete bet record
bet.delete()
```

### **3. Settlement (51s)**
- Winning bets: `payout_amount` set, wallet credited, WIN transaction
- Losing bets: `payout_amount = 0.00`, no wallet changes

---

## ⚠️ Edge Cases & Error Handling

### **1. System Crash During Settlement**
```python
def recover_settlement(round_obj):
    """
    Handle interrupted settlements
    """
    # Check if settlement was partially completed
    processed_bets = Bet.objects.filter(
        round=round_obj,
        payout_amount__isnull=False
    ).count()

    if processed_bets == 0:
        # No settlement started - restart
        calculate_payouts(round_obj)
    elif processed_bets < total_bets:
        # Partial settlement - rollback and restart
        rollback_partial_settlement(round_obj)
        calculate_payouts(round_obj)
```

### **2. Invalid Dice Values**
```python
def validate_dice_values(dice_values):
    """
    Ensure dice values are valid (1-6)
    """
    if not all(1 <= value <= 6 for value in dice_values):
        raise ValueError("Invalid dice values")

    if len(dice_values) != 6:
        raise ValueError("Must have exactly 6 dice")
```

### **3. Duplicate Processing Prevention**
```python
# Prevent double payouts
if bet.is_winner and bet.payout_amount > 0:
    logger.warning(f"Bet {bet.id} already processed - skipping")
    return
```

### **4. Wallet Balance Issues**
```python
def safe_wallet_credit(wallet, amount):
    """
    Safe wallet credit with validation
    """
    if amount <= 0:
        raise ValueError("Invalid credit amount")

    # Check for maximum balance limits
    if wallet.balance + amount > MAX_WALLET_BALANCE:
        raise ValueError("Wallet balance limit exceeded")

    wallet.add(amount)
```

---

## 📈 Settlement Statistics

### **Round-Level Aggregation**

```python
def calculate_round_statistics(round_obj):
    """
    Calculate settlement statistics
    """
    stats = Bet.objects.filter(round=round_obj).aggregate(
        total_bets=Count('id'),
        total_bet_amount=Sum('chip_amount'),
        total_winners=Count('id', filter=Q(is_winner=True)),
        total_payout=Sum('payout_amount'),
        total_unique_bettors=Count('user_id', distinct=True)
    )

    # Calculate house profit
    house_profit = stats['total_bet_amount'] - stats['total_payout']

    return {
        'total_bets': stats['total_bets'],
        'total_bet_amount': stats['total_bet_amount'],
        'total_winners': stats['total_winners'],
        'total_payout': stats['total_payout'],
        'house_profit': house_profit,
        'win_rate': (stats['total_winners'] / stats['total_bets']) * 100 if stats['total_bets'] > 0 else 0
    }
```

### **System-Level Monitoring**

```python
def monitor_system_balance():
    """
    Ensure system money balance integrity
    """
    # Total money in user wallets
    total_wallet_balance = Wallet.objects.aggregate(
        total=Sum('balance')
    )['total'] or 0

    # Total pending withdrawals
    total_pending_withdrawals = WithdrawRequest.objects.filter(
        status='PENDING'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # System should have enough to cover all withdrawals
    system_reserves = total_wallet_balance - total_pending_withdrawals

    return {
        'total_wallet_balance': total_wallet_balance,
        'pending_withdrawals': total_pending_withdrawals,
        'system_reserves': system_reserves
    }
```

---

## 🔐 Security Measures

### **1. Race Condition Prevention**
- Atomic database transactions
- Row-level locking on wallet updates
- Sequential bet processing

### **2. Fraud Prevention**
- Bet amount validation
- Balance checks before settlement
- Duplicate payout detection

### **3. Audit Trail**
- Complete transaction logging
- Settlement event logging
- Balance change tracking

### **4. System Monitoring**
- Real-time balance monitoring
- Settlement performance tracking
- Error alerting and recovery

---

## 🚨 Emergency Procedures

### **Settlement Failure Recovery**

```python
def emergency_settlement_recovery(round_id):
    """
    Manual settlement recovery for failed rounds
    """
    round_obj = GameRound.objects.get(round_id=round_id)

    # 1. Check current state
    settlement_status = check_settlement_status(round_obj)

    if settlement_status == 'NOT_STARTED':
        # Restart settlement
        calculate_payouts(round_obj)
    elif settlement_status == 'PARTIAL':
        # Rollback and restart
        rollback_partial_settlement(round_obj)
        calculate_payouts(round_obj)
    elif settlement_status == 'COMPLETED':
        # Verify integrity
        validate_settlement_integrity(round_obj)
```

### **Manual Payout Override (Admin Only)**

```python
def admin_manual_payout(bet_id, payout_amount, reason):
    """
    Admin override for settlement issues
    """
    bet = Bet.objects.get(id=bet_id)

    # Log manual intervention
    logger.warning(f"Manual payout override: Bet {bet_id}, Amount {payout_amount}, Reason: {reason}")

    # Process payout
    process_manual_payout(bet, payout_amount, reason)
```

---

## 📊 Settlement Performance Metrics

### **Key Performance Indicators**
- **Settlement Time**: Time to process all bets in a round
- **Success Rate**: Percentage of successful settlements
- **Error Rate**: Settlement failures per round
- **Average Payout Time**: Time from result to wallet credit

### **Monitoring Dashboard**
- Real-time settlement status
- Queue length and processing rates
- Error rates and failure patterns
- System resource utilization

---

## 🎯 Best Practices

### **1. Settlement Optimization**
- Batch processing for large rounds
- Index optimization on frequently queried fields
- Connection pooling for database operations

### **2. Error Recovery**
- Automatic retry mechanisms
- Manual intervention workflows
- Comprehensive error logging

### **3. Scalability**
- Horizontal scaling for high-volume rounds
- Caching for frequently accessed data
- Asynchronous processing for non-critical operations

---

*This document outlines the complete technical implementation of betting settlement in Gundu Ata. The system ensures 100% payout integrity, atomic operations, and comprehensive error handling for reliable financial processing.* 🎲💰⚙️