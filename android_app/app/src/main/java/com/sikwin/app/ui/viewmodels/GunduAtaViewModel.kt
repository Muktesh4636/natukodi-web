package com.sikwin.app.ui.viewmodels

import androidx.compose.runtime.getValue
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
            val json = JSONObject(errorBody)
            when {
                json.has("error") -> json.getString("error")
                json.has("message") -> json.getString("message")
                json.has("detail") -> json.getString("detail")
                else -> {
                    // Handle DRF serializer errors like {"field": ["error message"]}
                    val keys = json.keys()
                    if (keys.hasNext()) {
                        val firstKey = keys.next()
                        val value = json.get(firstKey)
                        if (value is org.json.JSONArray && value.length() > 0) {
                            value.getString(0)
                        } else if (value is org.json.JSONObject) {
                            // Nested object error
                            val nestedKeys = value.keys()
                            if (nestedKeys.hasNext()) {
                                val firstNestedKey = nestedKeys.next()
                                val nestedValue = value.get(firstNestedKey)
                                if (nestedValue is org.json.JSONArray && nestedValue.length() > 0) {
                                    nestedValue.getString(0)
                                } else {
                                    nestedValue.toString()
                                }
                            } else {
                                "Invalid input in $firstKey"
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
            "An unexpected error occurred. Please try again later."
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
    
    init {
        // Auto-login if token exists
        if (sessionManager.fetchAuthToken() != null) {
            loginSuccess = true
            fetchProfile()
            fetchWallet()
        }
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
                        
                        // Sync auth to Unity PlayerPrefs
                        sessionManager.syncAuthToUnity()
                        
                        // Send tokens to Unity if Unity is already running
                        try {
                            com.sikwin.app.utils.UnityTokenHelper.sendTokensToUnity(
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
                        // Note: We don't save password for OTP login
                        
                        // Sync auth to Unity PlayerPrefs
                        sessionManager.syncAuthToUnity()
                        
                        // Send tokens to Unity if Unity is already running
                        try {
                            com.sikwin.app.utils.UnityTokenHelper.sendTokensToUnity(
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
                    errorMessage = "Reset failed: ${parseError(errorBody)}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Registration failed: ${parseError(errorBody)}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    userProfile = response.body()
                }
            } catch (e: Exception) {
                errorMessage = e.message
            }
        }
    }

    fun fetchWallet() {
        viewModelScope.launch {
            try {
                val response = RetrofitClient.apiService.getWallet()
                if (response.isSuccessful) {
                    wallet = response.body()
                }
            } catch (e: Exception) {
                errorMessage = e.message
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
                errorMessage = e.message
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
                errorMessage = e.message
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
                errorMessage = e.message
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
                    bettingHistory = response.body() ?: emptyList()
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
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Failed to add bank detail: ${response.message()}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Failed to delete bank detail: ${response.message()}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Failed to submit UTR: ${parseError(errorBody)}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Upload failed: ${parseError(errorBody)}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Failed to update password: ${parseError(errorBody)}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                val response = RetrofitClient.apiService.updateProfile(data)
                if (response.isSuccessful) {
                    userProfile = response.body()
                    data["username"]?.let { sessionManager.saveUsername(it) }
                } else {
                    errorMessage = "Failed to update profile: ${response.message()}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Failed to update photo: ${response.message()}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    errorMessage = "Withdrawal failed: ${parseError(errorBody)}"
                }
            } catch (e: Exception) {
                errorMessage = "Error: ${e.message}"
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
                    onResult(false, "Failed to check status", null)
                }
            } catch (e: Exception) {
                onResult(false, e.message, null)
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
                        onResult(false, null, "TRY_AGAIN", "No reward found in response")
                    }
                } else {
                    val errorBody = response.errorBody()?.string()
                    onResult(false, null, "TRY_AGAIN", parseError(errorBody))
                }
            } catch (e: Exception) {
                onResult(false, null, "TRY_AGAIN", e.message)
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
                    onResult(false, "Failed to check status", null, null)
                }
            } catch (e: Exception) {
                onResult(false, e.message, null, null)
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
                        onResult(false, null, "No reward found in response")
                    }
                } else {
                    val errorBody = response.errorBody()?.string()
                    onResult(false, null, parseError(errorBody))
                }
            } catch (e: Exception) {
                onResult(false, null, e.message)
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
            // Clear Unity PlayerPrefs
            val unityPrefsName = "${context.packageName}.v2.playerprefs"
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
}
