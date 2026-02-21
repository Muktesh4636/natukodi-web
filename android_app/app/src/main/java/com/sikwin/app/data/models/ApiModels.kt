package com.sikwin.app.data.models

data class User(
    val id: Int,
    val username: String,
    val email: String,
    val phone_number: String?,
    val gender: String? = null,
    val telegram: String? = null,
    val facebook: String? = null,
    val address: String? = null,
    val date_of_birth: String? = null,
    val is_staff: Boolean,
    val profile_photo: String? = null,
    val referral_code: String? = null
)

data class AuthResponse(
    val access: String,
    val refresh: String,
    val user: User
)

data class Wallet(
    val balance: String,
    val unavaliable_balance: String = "0.00",
    val user: User? = null
)

data class Transaction(
    val id: Int,
    val transaction_type: String,
    val amount: String,
    val balance_before: String,
    val balance_after: String,
    val description: String,
    val created_at: String
)

data class DepositRequest(
    val id: Int,
    val amount: String,
    val status: String,
    val screenshot_url: String?,
    val admin_note: String?,
    val created_at: String
)

data class WithdrawRequest(
    val id: Int,
    val amount: String,
    val status: String,
    val withdrawal_method: String,
    val withdrawal_details: String,
    val admin_note: String?,
    val created_at: String
)

data class UserBankDetail(
    val id: Int,
    val account_name: String,
    val bank_name: String,
    val account_number: String,
    val ifsc_code: String,
    val upi_id: String?,
    val is_default: Boolean
)

data class PaymentMethod(
    val id: Int,
    val name: String,
    val method_type: String,
    val bank_name: String?,
    val account_number: String?,
    val account_name: String?,
    val ifsc_code: String?,
    val upi_id: String?,
    val qr_image: String?,
    val is_active: Boolean
)

data class ReferralData(
    val referral_code: String,
    val total_referrals: Int,
    val active_referrals: Int,
    val total_earnings: String,
    val current_milestone_bonus: String,
    val next_milestone: NextMilestone?,
    val milestones: List<Milestone>,
    val recent_bonuses: List<RecentBonus>
)

data class NextMilestone(
    val next_milestone: Int?,
    val next_bonus: Double,
    val current_progress: Int,
    val progress_percentage: Double
)

data class Milestone(
    val count: Int,
    val bonus: Int,
    val achieved: Boolean
)

data class RecentBonus(
    val amount: String,
    val description: String,
    val created_at: String
)

data class GameRound(
    val round_id: String,
    val status: String,
    val dice_result: String?,
    val created_at: String? = null
)

data class Bet(
    val id: Int,
    val round: GameRound,
    val number: Int,
    val chip_amount: String,
    val payout_amount: String,
    val is_winner: Boolean,
    val created_at: String
)

data class RecentRoundResult(
    val round_id: String,
    val dice_1: Int?,
    val dice_2: Int?,
    val dice_3: Int?,
    val dice_4: Int?,
    val dice_5: Int?,
    val dice_6: Int?,
    val dice_result: String?,
    val timestamp: String?
)
