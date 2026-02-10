# 💰 Gundu Ata Financial Rules & Money Management

Welcome to **Gundu Ata**! This document outlines the complete financial system, including how money enters and leaves the platform, betting mechanics, payout calculations, and administrative controls.

---

## 📊 System Overview

**Gundu Ata** operates on a **real-money betting system** where users can:
- **Deposit** money into their wallets
- **Place bets** on dice game numbers (1-6)
- **Win payouts** based on dice roll outcomes
- **Withdraw** their winnings
- **Earn bonuses** through referrals and daily rewards

### Core Principle: **100% Payout System**
There are **no hidden commissions** or house edges on game payouts. Players receive **100%** of their calculated winnings directly to their wallets.

---

## 💳 How Money Enters the System

### 1. **Deposits (Manual Admin Review)**
- **Method**: Users submit deposit requests with payment screenshots
- **Review Process**: Admins manually verify transactions and approve/reject requests
- **Credit Timing**: Money is added to wallet only after admin approval
- **Transaction Record**: Creates a `DEPOSIT` transaction entry

**Deposit Flow:**
```
User → Submit Request (Screenshot) → Admin Review → Approval → Wallet Credit → Transaction Log
```

### 2. **Referral Bonuses**
- **Trigger**: When a referred user makes their first deposit
- **Bonus Amount**: **10%** of the new user's first deposit amount
- **Example**: If referred user deposits ₹1,000, referrer gets ₹100 bonus
- **Transaction Record**: Creates a `REFERRAL_BONUS` transaction

**Referral Flow:**
```
New User → First Deposit ₹X → System → Referrer Gets ₹0.10X → Both Wallets Updated
```

### 3. **Daily Rewards (Spin Wheel)**
- **Frequency**: Once per day per user
- **Reward Types**:
  - **₹0** (Try Again)
  - **₹5, ₹10, ₹20** (Money Rewards)
- **Probabilities** (Current Settings):
  - ₹0: **20%** chance
  - ₹5: **60%** chance
  - ₹10: **15%** chance
  - ₹20: **5%** chance
- **Higher amounts (₹100, ₹500, ₹1000)** are disabled (0% chance)

**Daily Reward Flow:**
```
User → Spin Wheel → Random Selection → Wallet Credit → DailyReward Record
```

### 4. **Lucky Draw Bonuses (Bank Transfer Deposits)**
- **Trigger**: After successful bank transfer deposits
- **Bonus Amount**: **10%** of deposit amount
- **Example**: Deposit ₹1,000 → Get ₹100 lucky draw bonus

---

## 💸 How Money Leaves the System

### 1. **Bet Placement (Instant Deduction)**
- **Timing**: Money deducted immediately when bet is placed
- **Validation**: Must have sufficient wallet balance
- **Refund Option**: Can remove bet before betting closes (30 seconds)
- **Transaction Record**: Creates a `BET` transaction (negative amount)

**Bet Placement Flow:**
```
User → Place Bet ₹X → Wallet Debit ₹X → Bet Record Created → Transaction Log
```

### 2. **Withdrawals (Manual Admin Processing)**
- **Method**: Users request withdrawals with bank/UPI details
- **Review Process**: Admins manually process and complete transfers
- **Status**: `PENDING` → `APPROVED`/`REJECTED`
- **Transaction Record**: Creates a `WITHDRAW` transaction when processed

**Withdrawal Flow:**
```
User → Submit Withdrawal Request → Admin Review → Processing → Funds Transfer → Status Update
```

---

## 🎲 Betting & Payout Mechanics

### **Betting Rules**
- **Numbers**: 1-6 (dice faces)
- **Chip Values**: Any positive decimal amount (₹1, ₹5, ₹10, etc.)
- **Multiple Bets**: Users can bet on multiple numbers in the same round
- **Time Limit**: Betting closes at **30 seconds** into each round
- **Round Duration**: **80 seconds** total (30s betting + 51s result)

### **Winning Criteria**
A number becomes a **winner** if it appears **2 or more times** in the six-dice roll.

**Examples:**
- Roll: `4, 4, 4, 2, 2, 1` → Winners: **4** and **2**
- Roll: `1, 2, 3, 4, 5, 6` → No winners (all appear once)
- Roll: `3, 3, 3, 3, 3, 3` → Winner: **3** (appears 6 times)

### **Payout Calculation**
**Formula: `Payout = Bet Amount × Frequency`**

| Dice Frequency | Multiplier | Example (₹100 Bet) | Payout Amount |
|---------------|------------|-------------------|---------------|
| **2 Times** | 2x | ₹100 × 2 | ₹200 |
| **3 Times** | 3x | ₹100 × 3 | ₹300 |
| **4 Times** | 4x | ₹100 × 4 | ₹400 |
| **5 Times** | 5x | ₹100 × 5 | ₹500 |
| **6 Times** | 6x | ₹100 × 6 | ₹600 |

### **Payout Processing**
- **Timing**: Automatic payout when dice result is announced (51 seconds)
- **Amount**: **100%** of calculated payout (no deductions)
- **Wallet Credit**: Instant addition to winner's wallet
- **Transaction Record**: Creates a `WIN` transaction

**Win Flow:**
```
Dice Result → Calculate Winners → Apply Multipliers → Wallet Credit → WIN Transaction
```

---

## 📈 Transaction Types & Records

Every financial operation creates a detailed transaction record:

| Transaction Type | Amount Sign | Description | Trigger |
|-----------------|-------------|-------------|---------|
| `DEPOSIT` | **+** | Money added to wallet | Admin approves deposit request |
| `WITHDRAW` | **-** | Money removed from wallet | Admin processes withdrawal |
| `BET` | **-** | Bet placed | User places bet |
| `WIN` | **+** | Winnings credited | Dice result announced |
| `REFUND` | **+** | Bet refunded | User removes bet before closure |
| `REFERRAL_BONUS` | **+** | Referral earnings | Referred user deposits |
| `DAILY_REWARD` | **+** | Daily spin winnings | User claims daily reward |

**Transaction Data Tracked:**
- User ID and timestamp
- Amount and balance before/after
- Description of the operation
- Related entities (rounds, bets, etc.)

---

## 🔧 Administrative Controls

### **Deposit Management**
- **Manual Review**: All deposits require admin approval
- **Evidence**: Screenshots/payment proofs must be provided
- **Rejection**: Admins can reject invalid/fraudulent requests
- **Audit Trail**: All approvals/rejections are logged

### **Withdrawal Processing**
- **Verification**: Bank/UPI details must be provided
- **Manual Transfer**: Admins handle actual fund transfers
- **Status Tracking**: Complete audit trail of processing
- **Security**: Two-step verification for large withdrawals

### **Game Control (Admin Only)**
- **Dice Results**: Can be set manually or use random generation
- **Round Management**: Emergency pause/resume capabilities
- **Settings Control**: Betting times, round duration, etc.

### **Commission System (Legacy)**
- **Historical**: Previous system had 10% commission on payouts
- **Current Status**: **DISABLED** - All payouts are 100%
- **Records**: Old commission data preserved for audit purposes

---

## 🛡️ Security & Fair Play

### **Wallet Security**
- **Balance Validation**: Cannot bet more than available balance
- **Atomic Transactions**: All operations use database transactions
- **Audit Trail**: Every penny movement is tracked and logged

### **Game Fairness**
- **Cryptographic Random**: Dice results use secure random generation
- **No Manipulation**: Results cannot be changed after betting closes
- **Transparent Rules**: All payout calculations are deterministic

### **Anti-Fraud Measures**
- **OTP Verification**: Phone number verification for all accounts
- **Deposit Verification**: Manual screenshot review for deposits
- **Transaction Limits**: Withdrawal limits and velocity controls
- **Account Monitoring**: Suspicious activity detection

---

## 📊 Financial Reporting

### **User-Level Reports**
- **Transaction History**: Complete list of all financial operations
- **Betting History**: Detailed bet and win/loss records
- **Wallet Balance**: Real-time balance tracking
- **Referral Earnings**: Track referral bonus history

### **Admin Reports**
- **Daily/Monthly Volume**: Total bets, deposits, withdrawals
- **Profit/Loss Analysis**: System-wide financial performance
- **User Activity**: Active users, betting patterns
- **Pending Actions**: Deposits/withdrawals awaiting processing

---

## ⚠️ Important Notes

### **No Guarantees**
- **Betting Risks**: All betting involves risk of loss
- **No Refunds**: Once betting closes, bets cannot be refunded
- **Processing Times**: Deposits/withdrawals may take time for verification

### **Responsible Gaming**
- **Self-Control**: Set personal betting limits
- **Balance Awareness**: Monitor wallet balance regularly
- **Break Taking**: Take breaks during long gaming sessions

### **Technical Considerations**
- **Real-Time Updates**: Wallet balances update instantly
- **Offline Handling**: System handles network interruptions gracefully
- **Data Persistence**: All transactions are permanently recorded

---

## 📞 Support & Disputes

### **Financial Disputes**
- **Transaction Review**: All operations are logged and auditable
- **Admin Intervention**: Contact support for disputed transactions
- **Evidence Required**: Provide screenshots/transaction IDs

### **Technical Issues**
- **Balance Discrepancies**: Automatic reconciliation available
- **Failed Transactions**: Retry mechanisms in place
- **System Outages**: Emergency procedures documented

---

*This document outlines the complete financial ecosystem of Gundu Ata. All rules are enforced automatically by the system to ensure fair play and financial integrity.* 🎲💰