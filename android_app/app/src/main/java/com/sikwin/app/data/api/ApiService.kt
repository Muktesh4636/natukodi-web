package com.sikwin.app.data.api

import com.sikwin.app.data.models.*
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.*

interface ApiService {
    @POST("auth/login/")
    suspend fun login(@Body credentials: Map<String, String>): Response<AuthResponse>

    @POST("auth/otp/send/")
    suspend fun sendOtp(@Body data: Map<String, String>): Response<Map<String, Any>>

    @POST("auth/otp/verify-login/")
    suspend fun verifyOtpLogin(@Body data: Map<String, String>): Response<AuthResponse>

    @POST("auth/register/")
    suspend fun register(@Body data: Map<String, String>): Response<AuthResponse>

    @POST("auth/password/reset/")
    suspend fun resetPassword(@Body data: Map<String, String>): Response<Map<String, Any>>

    @POST("auth/token/refresh/")
    suspend fun refreshToken(@Body data: Map<String, String>): Response<Map<String, String>>

    @GET("auth/profile/")
    suspend fun getProfile(): Response<User>

    @POST("auth/profile/")
    suspend fun updateProfile(@Body data: Map<String, String>): Response<User>

    @Multipart
    @POST("auth/profile/photo/")
    suspend fun updateProfilePhoto(@Part photo: MultipartBody.Part): Response<User>

    @GET("auth/wallet/")
    suspend fun getWallet(): Response<Wallet>

    @GET("auth/transactions/")
    suspend fun getTransactions(): Response<List<Transaction>>

    @GET("auth/deposits/mine/")
    suspend fun getMyDeposits(): Response<List<DepositRequest>>

    @Multipart
    @POST("auth/deposits/upload-proof/")
    suspend fun uploadDepositProof(
        @Part("amount") amount: String,
        @Part screenshot: MultipartBody.Part
    ): Response<DepositRequest>

    @POST("auth/deposits/submit-utr/")
    suspend fun submitUtr(@Body data: Map<String, String>): Response<DepositRequest>

    @POST("auth/withdraws/initiate/")
    suspend fun initiateWithdraw(@Body data: Map<String, String>): Response<WithdrawRequest>

    @GET("auth/withdraws/mine/")
    suspend fun getMyWithdrawals(): Response<List<WithdrawRequest>>
    
    @GET("auth/payment-methods/")
    suspend fun getPaymentMethods(): Response<List<PaymentMethod>>

    @GET("auth/bank-details/")
    suspend fun getBankDetails(): Response<List<UserBankDetail>>

    @POST("auth/bank-details/")
    suspend fun addBankDetail(@Body data: @JvmSuppressWildcards Map<String, Any>): Response<UserBankDetail>
    
    @GET("auth/referral-data/")
    suspend fun getReferralData(): Response<ReferralData>

    @GET("auth/daily-reward/")
    suspend fun checkDailyRewardStatus(): Response<Map<String, Any>>

    @POST("auth/daily-reward/")
    suspend fun claimDailyReward(): Response<Map<String, Any>>
    
    @GET("auth/lucky-draw/")
    suspend fun checkLuckyDrawStatus(): Response<Map<String, Any>>
    
    @POST("auth/lucky-draw/")
    suspend fun claimLuckyDraw(): Response<Map<String, Any>>

    @GET("game/round/")
    suspend fun getCurrentRound(): Response<Map<String, Any>>

    @GET("game/betting-history/")
    suspend fun getBettingHistory(): Response<List<Bet>>

    @DELETE("auth/bank-details/{id}/")
    suspend fun deleteBankDetail(@Path("id") id: Int): Response<Unit>
    
    // Optional: Send contacts to backend (uncomment if you want to sync contacts)
    // @POST("auth/contacts/")
    // suspend fun syncContacts(@Body data: Map<String, String>): Response<Map<String, Any>>
}
