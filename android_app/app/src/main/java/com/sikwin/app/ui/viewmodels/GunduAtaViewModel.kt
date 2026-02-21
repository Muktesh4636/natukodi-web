package com.sikwin.app.ui.viewmodels

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sikwin.app.data.api.RetrofitClient
import com.sikwin.app.data.auth.SessionManager
import com.sikwin.app.data.models.*
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class GunduAtaViewModel(private val sessionManager: SessionManager) : ViewModel() {

    var isLoading by mutableStateOf(false)
    var errorMessage by mutableStateOf<String?>(null)

    fun clearError() {
        errorMessage = null
    }

    private fun parseError(errorBody: String?): String {
        if (errorBody.isNullOrEmpty()) return "Something went wrong. Please try again."
        return try {
            val raw = try {
                val json = JSONObject(errorBody)
                when {
                    json.has("error") -> json.getString("error")
                    json.has("message") -> json.getString("message")
                    json.has("detail") -> json.getString("detail")
                    else -> {
                        val keys = json.keys()
                        if (keys.hasNext()) {
                            val firstKey = keys.next()
                            val value = json.get(firstKey)
                            if (value is org.json.JSONArray && value.length() > 0) {
                                value.getString(0)
                            } else if (value is org.json.JSONObject) {
                                val nestedKeys = value.keys()
                                if (nestedKeys.hasNext()) {
                                    val firstNestedKey = nestedKeys.next()
                                    value.get(firstNestedKey).toString()
                                } else {
                                    "Invalid input. Please try again."
                                }
                            } else {
                                value.toString()
                            }
                        } else {
                            "An unexpected error occurred."
                        }
                    }
                }
            } catch (e: Exception) {
                if (errorBody.length < 200 && !errorBody.trim().startsWith("{")) errorBody.trim()
                else "Something went wrong. Please try again."
            }
            sanitizeErrorMessage(raw)
        } catch (e: Exception) {
            "Something went wrong. Please try again."
        }
    }

    private fun sanitizeErrorMessage(raw: String): String {
        if (raw.isBlank()) return "Something went wrong. Please try again."
        
        // Catch HTML responses
        if (raw.trim().startsWith("<!doctype", ignoreCase = true) || 
            raw.trim().startsWith("<html", ignoreCase = true)) {
            val lower = raw.lowercase()
            return when {
                lower.contains("413") || lower.contains("too large") -> "The file you are trying to upload is too large. Please use a smaller file (max 10MB)."
                lower.contains("502") || lower.contains("bad gateway") -> "Server is busy. Please try again later."
                lower.contains("504") || lower.contains("gateway timeout") -> "Server timeout. Please try again."
                else -> "An unexpected server error occurred. Please try again."
            }
        }

        val lower = raw.lowercase()
        return when {
            lower.contains("already has a pending request") || 
            lower.contains("pending withdraw request") -> "Withdrawal already in processing"
            lower.contains("500") || lower.contains("internal server error") -> "Server error. Please try again later."
            lower.contains("502") || lower.contains("bad gateway") -> "Server is busy. Please try again later."
            lower.contains("503") || lower.contains("service unavailable") -> "Service temporarily unavailable. Please try again."
            lower.contains("404") || lower.contains("not found") -> "Request could not be completed. Please try again."
            lower.contains("403") || lower.contains("forbidden") -> "Access denied. Please try again."
            lower.contains("401") || lower.contains("unauthorized") || lower.contains("authentication") -> "Please sign in again."
            lower.contains("413") || lower.contains("too large") -> "The file you are trying to upload is too large. Please use a smaller file."
            lower.contains("connection refused") || lower.contains("failed to connect") -> "Unable to connect. Please check your network."
            lower.contains("timeout") || lower.contains("timed out") -> "Request timed out. Please try again."
            else -> raw
        }
    }

    private fun handleException(e: Exception): String {
        android.util.Log.e("GunduAtaViewModel", "Exception: ${e.message}", e)
        return when (e) {
            is java.net.UnknownHostException -> "No internet connection. Please check your network."
            is java.net.SocketTimeoutException -> "Connection timed out. Please try again."
            is java.net.ConnectException -> "Unable to connect to server. Please try again later."
            is retrofit2.HttpException -> "Server error. Please try again later."
            else -> "An unexpected error occurred. Please try again."
        }
    }
    
    var userProfile by mutableStateOf<User?>(null)
    var wallet by mutableStateOf<Wallet?>(null)
    var transactions by mutableStateOf<List<Transaction>>(emptyList())
    var depositRequests by mutableStateOf<List<DepositRequest>>(emptyList())
    var withdrawRequests by mutableStateOf<List<WithdrawRequest>>(emptyList())
    var paymentMethods by mutableStateOf<List<PaymentMethod>>(emptyList())
    var bettingHistory by mutableStateOf<List<Bet>>(emptyList())
    var referralData by mutableStateOf<ReferralData?>(null)
    
    var otpSent by mutableStateOf(false)
    var isVerifyingOtp by mutableStateOf(false)
    
    var bankDetails by mutableStateOf<List<UserBankDetail>>(emptyList())
    
    var loginSuccess by mutableStateOf(false)
    
    // Logo click tracking
    var logoClickCount by mutableIntStateOf(0)
    
    fun incrementLogoClickCount() {
        logoClickCount++
    }
    
    // App Update state
    var showUpdateDialog by mutableStateOf(false)
    var updateUrl by mutableStateOf<String?>(null)
    var isForceUpdate by mutableStateOf(false)
    var latestVersionName by mutableStateOf<String?>(null)
    
    var recentResults by mutableStateOf<List<RecentRoundResult>>(emptyList())
    
    // Timer pre-loading state
    var preLoadedTimer by mutableStateOf<Int?>(null)
    var preLoadedStatus by mutableStateOf<String?>(null)
    var preLoadedRoundId by mutableStateOf<String?>(null)
    private var timerJob: kotlinx.coroutines.Job? = null

    fun startTimerPreloading() {
        if (timerJob != null && timerJob?.isActive == true) return
        
        timerJob = viewModelScope.launch {
            while (true) {
                try {
                    val response = RetrofitClient.apiService.getCurrentRound()
                    if (response.isSuccessful) {
                        val data = response.body()
                        preLoadedTimer = (data?.get("timer") as? Double)?.toInt() ?: (data?.get("timer") as? Int)
                        preLoadedStatus = data?.get("status") as? String
                        preLoadedRoundId = data?.get("round_id") as? String
                        
                        // Sync to Unity immediately so it's ready
                        preLoadedTimer?.let { t ->
                            preLoadedStatus?.let { s ->
                                preLoadedRoundId?.let { r ->
                                    syncTimerToUnity(t, s, r)
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    android.util.Log.e("GunduAtaViewModel", "Timer pre-load failed: ${e.message}")
                }
                kotlinx.coroutines.delay(500) // Update every 500ms for ultra-fresh 0-lag sync
            }
        }
    }

    fun stopTimerPreloading() {
        timerJob?.cancel()
        timerJob = null
    }

    private fun syncTimerToUnity(timer: Int, status: String, roundId: String) {
        try {
            // We use PlayerPrefs via a helper or direct SharedPreferences
            // This ensures Unity sees the timer the moment it starts
            val sessionManager = com.sikwin.app.data.api.RetrofitClient.getSessionManager()
            if (sessionManager != null) {
                sessionManager.syncAuthToUnity() // Use existing helper to get context/prefs
                
                // Now add the timer specific fields
                val context = sessionManager.getContext()
                val standalonePackageName = "com.company.dicegame"
                val unityPrefsName = "$standalonePackageName.v2.playerprefs"
                val unityPrefs = context.getSharedPreferences(unityPrefsName, android.content.Context.MODE_PRIVATE)
                unityPrefs.edit()
                    .putInt("preloaded_timer", timer)
                    .putString("preloaded_status", status)
                    .putString("preloaded_round_id", roundId)
                    .putString("preloaded_timestamp", System.currentTimeMillis().toString())
                    .apply()
            }
        } catch (e: Exception) {
            android.util.Log.e("GunduAtaViewModel", "Failed to sync timer to Unity: ${e.message}")
        }
    }

    // Check if session is still valid
    fun checkSession() {
        if (sessionManager.fetchAuthToken() == null) {
            loginSuccess = false
            userProfile = null
            wallet = null
        }
    }
    
    init {
        // Initialize RetrofitClient with session manager
        RetrofitClient.init(sessionManager)

        // Sync auth to Unity PlayerPrefs on init to ensure consistency
        sessionManager.syncAuthToUnity()
        
        loginSuccess = sessionManager.fetchAuthToken() != null
    }

    fun login(username: String, password: String) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.login(mapOf("username" to username, "password" to password))
                if (response.isSuccessful) {
                    val authResponse = response.body()
                    authResponse?.let {
                        sessionManager.saveAuthToken(it.access)
                        sessionManager.saveRefreshToken(it.refresh)
                        sessionManager.saveUsername(it.user.username)
                        sessionManager.saveUserId(it.user.id)
                        sessionManager.savePassword(password)
                        sessionManager.saveReferralCode(it.user.referral_code)
                        
                        // Sync auth to Unity PlayerPrefs
                        sessionManager.syncAuthToUnity()
                        
                        // Send tokens to Unity if Unity is already running
                        try {
                            com.sikwin.app.utils.UnityTokenHelper.sendTokensToUnity(
                                sessionManager.getContext(),
                                it.access,
                                it.refresh,
                                it.user.username ?: ""
                            )
                        } catch (e: Exception) {
                            // Unity might not be running yet, that's okay
                            android.util.Log.d("GunduAtaViewModel", "Unity not running, tokens will be sent when Unity starts: ${e.message}")
                        }
                        
                        userProfile = it.user
                        loginSuccess = true
                    }
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun sendOtp(phoneNumber: String) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.sendOtp(mapOf("phone_number" to phoneNumber))
                if (response.isSuccessful) {
                    otpSent = true
                    errorMessage = null
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun verifyOtpLogin(phoneNumber: String, otpCode: String) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.verifyOtpLogin(mapOf(
                    "phone_number" to phoneNumber,
                    "otp_code" to otpCode
                ))
                if (response.isSuccessful) {
                    val authResponse = response.body()
                    authResponse?.let {
                        sessionManager.saveAuthToken(it.access)
                        sessionManager.saveRefreshToken(it.refresh)
                        sessionManager.saveUsername(it.user.username)
                        sessionManager.saveUserId(it.user.id)
                        sessionManager.saveReferralCode(it.user.referral_code)
                        // Note: We don't save password for OTP login
                        
                        // Sync auth to Unity PlayerPrefs
                        sessionManager.syncAuthToUnity()
                        
                        // Send tokens to Unity if Unity is already running
                        try {
                            com.sikwin.app.utils.UnityTokenHelper.sendTokensToUnity(
                                sessionManager.getContext(),
                                it.access,
                                it.refresh,
                                it.user.username ?: ""
                            )
                        } catch (e: Exception) {
                            // Unity might not be running yet, that's okay
                            android.util.Log.d("GunduAtaViewModel", "Unity not running, tokens will be sent when Unity starts: ${e.message}")
                        }
                        
                        userProfile = it.user
                        sessionManager.saveReferralCode(it.user.referral_code)
                        loginSuccess = true
                        otpSent = false // Reset OTP state
                    }
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun clearOtpState() {
        otpSent = false
        errorMessage = null
    }

    fun resetPassword(phoneNumber: String, otpCode: String, newPassword: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val data = mapOf(
                    "phone_number" to phoneNumber,
                    "otp_code" to otpCode,
                    "new_password" to newPassword
                )
                val response = RetrofitClient.apiService.resetPassword(data)
                if (response.isSuccessful) {
                    onSuccess()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun register(data: Map<String, String>) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.register(data)
                if (response.isSuccessful) {
                    val authResponse = response.body()
                    authResponse?.let {
                        sessionManager.saveAuthToken(it.access)
                        sessionManager.saveRefreshToken(it.refresh)
                        sessionManager.saveUsername(it.user.username)
                        sessionManager.saveUserId(it.user.id)
                        data["password"]?.let { pass -> sessionManager.savePassword(pass) }
                        
                        // Sync auth to Unity PlayerPrefs
                        sessionManager.syncAuthToUnity()
                        
                        // Send tokens to Unity if Unity is already running
                        try {
                            com.sikwin.app.utils.UnityTokenHelper.sendTokensToUnity(
                                sessionManager.getContext(),
                                it.access,
                                it.refresh,
                                it.user.username ?: ""
                            )
                        } catch (e: Exception) {
                            // Unity might not be running yet, that's okay
                            android.util.Log.d("GunduAtaViewModel", "Unity not running, tokens will be sent when Unity starts: ${e.message}")
                        }
                        
                        userProfile = it.user
                        sessionManager.saveReferralCode(it.user.referral_code)
                        loginSuccess = true
                    }
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun fetchProfile() {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.getProfile()
                if (response.isSuccessful) {
                    val profile = response.body()
                    userProfile = profile
                    sessionManager.saveReferralCode(profile?.referral_code)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            }
        }
    }

    fun fetchWallet() {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.getWallet()
                if (response.isSuccessful) {
                    wallet = response.body()
                    // Re-fetch betting history to update ranking whenever wallet is refreshed
                    fetchBettingHistory()
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            }
        }
    }

    fun fetchTransactions() {
        viewModelScope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getTransactions()
                if (response.isSuccessful) {
                    transactions = response.body() ?: emptyList()
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun fetchDeposits() {
        viewModelScope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getMyDeposits()
                if (response.isSuccessful) {
                    depositRequests = response.body() ?: emptyList()
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun fetchWithdrawals() {
        viewModelScope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getMyWithdrawals()
                if (response.isSuccessful) {
                    withdrawRequests = response.body() ?: emptyList()
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun fetchPaymentMethods() {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.getPaymentMethods()
                if (response.isSuccessful) {
                    paymentMethods = response.body() ?: emptyList()
                }
            } catch (e: Exception) {
                // Log and ignore background fetch errors to prevent technical jargon in UI
                android.util.Log.e("GunduAtaViewModel", "Fetch payment methods failed: ${e.message}")
            }
        }
    }

    fun fetchBankDetails() {
        viewModelScope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getBankDetails()
                if (response.isSuccessful) {
                    bankDetails = response.body() ?: emptyList()
                }
            } catch (e: Exception) {
                android.util.Log.e("GunduAtaViewModel", "Fetch bank details failed: ${e.message}")
            } finally {
                isLoading = false
            }
        }
    }

    fun fetchBettingHistory() {
        viewModelScope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getBettingHistory()
                if (response.isSuccessful) {
                    val history = response.body() ?: emptyList()
                    bettingHistory = history
                    
                    // Calculate total rotation from betting history to update ranking
                    // chip_amount is the field name in the Bet model
                    val totalRotation = history.sumOf { it.chip_amount.toDoubleOrNull() ?: 0.0 }
                    userRotationMoney = totalRotation
                    calculateUserRank()
                }
            } catch (e: Exception) {
                android.util.Log.e("GunduAtaViewModel", "Fetch betting history failed: ${e.message}")
            } finally {
                isLoading = false
            }
        }
    }

    fun fetchReferralData() {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.getReferralData()
                if (response.isSuccessful) {
                    referralData = response.body()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun addBankDetail(data: Map<String, Any>, onSuccess: () -> Unit) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.addBankDetail(data)
                if (response.isSuccessful) {
                    fetchBankDetails()
                    onSuccess()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody).ifEmpty { "Could not add bank account. Please try again." }
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun deleteBankDetail(id: Int) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.deleteBankDetail(id)
                if (response.isSuccessful) {
                    fetchBankDetails()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody).ifEmpty { "Could not remove bank account. Please try again." }
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun submitUtr(amount: String, utr: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.submitUtr(mapOf("amount" to amount, "utr" to utr))
                if (response.isSuccessful) {
                    onSuccess()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun uploadDepositProof(amount: String, uri: android.net.Uri, context: android.content.Context, onSuccess: () -> Unit) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val contentResolver = context.contentResolver
                val inputStream = contentResolver.openInputStream(uri)
                val bytes = inputStream?.readBytes() ?: throw Exception("Failed to read image")
                inputStream.close()

                val requestFile = bytes.toRequestBody("image/*".toMediaTypeOrNull(), 0, bytes.size)
                val body = MultipartBody.Part.createFormData("screenshot", "screenshot.jpg", requestFile)

                val response = RetrofitClient.apiService.uploadDepositProof(amount, body)
                if (response.isSuccessful) {
                    onSuccess()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun updateUsername(newUsername: String) {
        updateProfile(mapOf("username" to newUsername))
    }

    fun updatePassword(currentPassword: String, newPassword: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val data = mapOf(
                    "current_password" to currentPassword,
                    "new_password" to newPassword
                )
                val response = RetrofitClient.apiService.updateProfile(data)
                if (response.isSuccessful) {
                    onSuccess()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun updateProfile(data: Map<String, String>) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                // Ensure gender is uppercase if present
                val processedData = data.toMutableMap()
                if (processedData.containsKey("gender")) {
                    processedData["gender"] = processedData["gender"]?.uppercase() ?: ""
                }
                
                // Map "Name" to "username" if it comes from the UI as "Name"
                if (processedData.containsKey("Name")) {
                    processedData["username"] = processedData.remove("Name") ?: ""
                }
                
                val response = RetrofitClient.apiService.updateProfile(processedData)
                if (response.isSuccessful) {
                    userProfile = response.body()
                    processedData["username"]?.let { sessionManager.saveUsername(it) }
                    // Re-fetch profile to ensure UI is in sync with server state
                    fetchProfile()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody).ifEmpty { "Could not update profile. Please try again." }
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun updateProfilePhoto(photo: okhttp3.MultipartBody.Part) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.updateProfilePhoto(photo)
                if (response.isSuccessful) {
                    userProfile = response.body()
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody).ifEmpty { "Could not update photo. Please try again." }
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }

    fun initiateWithdraw(amount: String, bankAccount: UserBankDetail, onSuccess: () -> Unit) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val details = "Bank: ${bankAccount.bank_name}, Acc: ${bankAccount.account_number}, IFSC: ${bankAccount.ifsc_code}"
                val data = mapOf(
                    "amount" to amount,
                    "withdrawal_method" to "Bank Account",
                    "withdrawal_details" to details
                )
                val response = RetrofitClient.apiService.initiateWithdraw(data)
                if (response.isSuccessful) {
                    onSuccess()
                    fetchWallet() // Refresh balance
                } else {
                    val errorBody = response.errorBody()?.string()
                    errorMessage = parseError(errorBody)
                }
            } catch (e: Exception) {
                errorMessage = handleException(e)
            } finally {
                isLoading = false
            }
        }
    }
    
    fun checkDailyRewardStatus(onResult: (Boolean, String?, String?) -> Unit) {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.checkDailyRewardStatus()
                if (response.isSuccessful) {
                    val body = response.body()
                    val claimed = body?.get("claimed") as? Boolean ?: false
                    val message = body?.get("message") as? String
                    val reward = body?.get("reward") as? Map<*, *>
                    val amount = reward?.get("amount")?.toString()
                    onResult(claimed, message, amount)
                } else {
                    onResult(false, "Unable to check reward status. Please try again.", null)
                }
            } catch (e: Exception) {
                onResult(false, handleException(e), null)
            }
        }
    }

    fun claimDailyReward(onResult: (Boolean, Int?, String, String?) -> Unit) {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.claimDailyReward()
                if (response.isSuccessful) {
                    val body = response.body()
                    val reward = body?.get("daily_reward") as? Map<*, *> ?: body?.get("reward") as? Map<*, *>
                    
                    if (reward != null) {
                        val amountStr = reward["amount"]?.toString() ?: "0"
                        val amount = amountStr.toDoubleOrNull()?.toInt() ?: 0
                        val type = reward["type"]?.toString() ?: "MONEY"
                        val message = body?.get("message") as? String ?: "Reward claimed"
                        
                        // Refresh wallet balance after claiming
                        fetchWallet()
                        
                        onResult(true, amount, type, message)
                    } else {
                        onResult(false, null, "TRY_AGAIN", "Something went wrong. Please try again.")
                    }
                } else {
                    val errorBody = response.errorBody()?.string()
                    onResult(false, null, "TRY_AGAIN", parseError(errorBody))
                }
            } catch (e: Exception) {
                onResult(false, null, "TRY_AGAIN", handleException(e))
            }
        }
    }

    fun checkLuckyDrawStatus(onResult: (Boolean, String?, String?, Double?) -> Unit) {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.checkLuckyDrawStatus()
                if (response.isSuccessful) {
                    val body = response.body()
                    val claimed = body?.get("claimed") as? Boolean ?: false
                    val message = body?.get("message") as? String
                    val reward = body?.get("reward") as? Map<*, *>
                    val amount = reward?.get("amount")?.toString()
                    val depositAmount = body?.get("deposit_amount")?.toString()?.toDoubleOrNull()
                    onResult(claimed, message, amount, depositAmount)
                } else {
                    onResult(false, "Unable to check lucky draw status. Please try again.", null, null)
                }
            } catch (e: Exception) {
                onResult(false, handleException(e), null, null)
            }
        }
    }

    fun claimLuckyDraw(onResult: (Boolean, Int?, String?) -> Unit) {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.claimLuckyDraw()
                if (response.isSuccessful) {
                    val body = response.body()
                    val reward = body?.get("lucky_draw") as? Map<*, *> ?: body?.get("reward") as? Map<*, *>
                    
                    if (reward != null) {
                        val amountStr = reward["amount"]?.toString() ?: "0"
                        val amount = amountStr.toDoubleOrNull()?.toInt() ?: 0
                        val message = body?.get("message") as? String ?: "Reward claimed"
                        
                        // Refresh wallet balance after claiming
                        fetchWallet()
                        
                        onResult(true, amount, message)
                    } else {
                        onResult(false, null, "Something went wrong. Please try again.")
                    }
                } else {
                    val errorBody = response.errorBody()?.string()
                    onResult(false, null, parseError(errorBody))
                }
            } catch (e: Exception) {
                onResult(false, null, handleException(e))
            }
        }
    }

    // Optional: Sync contacts to backend
    // Uncomment this function and the API endpoint if you want to send contacts to server
    /*
    fun syncContacts(contactsJson: String, onSuccess: () -> Unit = {}, onError: (String) -> Unit = {}) {
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = RetrofitClient.apiService.syncContacts(mapOf("contacts" to contactsJson))
                if (response.isSuccessful) {
                    onSuccess()
                } else {
                    val errorBody = response.errorBody()?.string()
                    val error = parseError(errorBody)
                    errorMessage = error
                    onError(error)
                }
            } catch (e: Exception) {
                val error = e.message ?: "Failed to sync contacts"
                errorMessage = error
                onError(error)
            } finally {
                isLoading = false
            }
        }
    }
    */

    fun logout() {
        sessionManager.logout()
        
        // Notify Unity to logout
        try {
            com.sikwin.app.utils.UnityTokenHelper.sendLogoutToUnity(sessionManager.getContext())
        } catch (e: Exception) {
            android.util.Log.d("GunduAtaViewModel", "Unity not running, logout signal skipped: ${e.message}")
        }

        userProfile = null
        wallet = null
        transactions = emptyList()
        depositRequests = emptyList()
        withdrawRequests = emptyList()
        errorMessage = null
        loginSuccess = false
    }

    fun clearUnityAuthentication(context: android.content.Context) {
        try {
            // Clear Unity PlayerPrefs for standalone app
            val standalonePackageName = "com.company.dicegame"
            val unityPrefsName = "$standalonePackageName.v2.playerprefs"
            val unityPrefs = context.getSharedPreferences(unityPrefsName, android.content.Context.MODE_PRIVATE)
            unityPrefs.edit().clear().apply()

            // Also set logout flag for Unity
            unityPrefs.edit()
                .putString("is_logged_in", "false")
                .putString("logout_requested", "true")
                .putLong("logout_timestamp", System.currentTimeMillis())
                .apply()
        } catch (e: Exception) {
            // Ignore errors when clearing Unity prefs
        }
    }

    fun isNewUser(): Boolean {
        return sessionManager.isNewUser()
    }

    fun markUserAsNew() {
        sessionManager.setNewUser(true)
    }

    fun markUserAsNotNew() {
        sessionManager.setNewUser(false)
    }

    fun checkForUpdates(currentVersionCode: Int) {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.getAppVersion()
                if (response.isSuccessful) {
                    val data = response.body()
                    val latestVersionCode = (data?.get("version_code") as? Double)?.toInt() ?: (data?.get("version_code") as? Int) ?: 0
                    
                    if (latestVersionCode > currentVersionCode) {
                        latestVersionName = data?.get("version_name") as? String
                        updateUrl = data?.get("download_url") as? String
                        isForceUpdate = data?.get("force_update") as? Boolean ?: false
                        showUpdateDialog = true
                    }
                }
            } catch (e: Exception) {
                android.util.Log.e("GunduAtaViewModel", "Update check failed: ${e.message}")
            }
        }
    }

    fun fetchRecentRoundResults(count: Int = 20) {
        viewModelScope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getRecentRoundResults(count)
                if (response.isSuccessful) {
                    recentResults = response.body() ?: emptyList()
                }
            } catch (e: Exception) {
                android.util.Log.e("GunduAtaViewModel", "Fetch recent results failed: ${e.message}")
            } finally {
                isLoading = false
            }
        }
    }

    // Leaderboard and Ranking logic
    var userRank by mutableIntStateOf(0)
    var userRotationMoney by mutableStateOf(0.0)
    var leaderboardPlayers by mutableStateOf<List<Map<String, Any>>>(emptyList())
    var leaderboardPrizes by mutableStateOf<Map<String, String>>(mapOf("1st" to "₹1,000", "2nd" to "₹500", "3rd" to "₹100"))

    fun fetchLeaderboard() {
        viewModelScope.launch {
            isLoading = true
            try {
                val response = RetrofitClient.apiService.getLeaderboard()
                if (response.isSuccessful) {
                    val data = response.body()
                    val leaderboard = data?.get("leaderboard") as? List<Map<String, Any>> ?: emptyList()
                    leaderboardPlayers = leaderboard
                    
                    val userStats = data?.get("user_stats") as? Map<String, Any>
                    userRank = (userStats?.get("rank") as? Double)?.toInt() ?: (userStats?.get("rank") as? Int) ?: 0
                    userRotationMoney = (userStats?.get("turnover") as? Double) ?: (userStats?.get("turnover") as? Int)?.toDouble() ?: 0.0

                    val prizes = data?.get("prizes") as? Map<String, String>
                    if (prizes != null) {
                        leaderboardPrizes = prizes
                    }
                }
            } catch (e: Exception) {
                android.util.Log.e("GunduAtaViewModel", "Fetch leaderboard failed: ${e.message}")
            } finally {
                isLoading = false
            }
        }
    }

    fun updateUserRotation(amount: Double) {
        userRotationMoney += amount
        calculateUserRank()
    }

    private fun calculateUserRank() {
        // Logic: Rank decreases (gets better) as rotation money increases.
        // If rotation is 0, rank is 0 (unranked).
        if (userRotationMoney <= 0) {
            userRank = 0
            return
        }

        // Stable ranking logic based on rotation money:
        // Rank 1: > 1,00,000 rotation
        // Rank 2: > 75,000
        // Rank 3: > 50,000
        // Rank 4: > 40,000
        // Rank 5: > 30,000
        // Rank 6: > 25,000
        // Rank 7: > 20,000
        // Rank 8: > 15,000
        // Rank 9: > 10,000
        // Rank 10: > 5,000
        userRank = when {
            userRotationMoney > 100000 -> 1
            userRotationMoney > 75000 -> 2
            userRotationMoney > 50000 -> 3
            userRotationMoney > 40000 -> 4
            userRotationMoney > 30000 -> 5
            userRotationMoney > 25000 -> 6
            userRotationMoney > 20000 -> 7
            userRotationMoney > 15000 -> 8
            userRotationMoney > 10000 -> 9
            userRotationMoney > 5000 -> 10
            else -> {
                // For lower rotations, calculate a stable rank between 11 and 100
                // Higher rotation = lower rank number
                val calculated = 100 - (userRotationMoney / 5000 * 90).toInt()
                calculated.coerceIn(11, 100)
            }
        }
    }
}
