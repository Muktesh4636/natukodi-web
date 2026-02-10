package com.sikwin.app.navigation

import android.app.Activity
import android.content.Intent
import android.net.Uri
import java.io.File
import java.io.FileOutputStream
import android.widget.Toast
import androidx.core.content.FileProvider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.sikwin.app.data.auth.SessionManager
import com.sikwin.app.ui.screens.*
import com.sikwin.app.ui.screens.AffiliateScreen
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel
import androidx.compose.runtime.*
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.text.font.FontWeight
import com.sikwin.app.ui.theme.PrimaryYellow

@Composable
fun AppNavigation(
    navController: NavHostController,
    viewModel: GunduAtaViewModel,
    sessionManager: SessionManager
) {
    val context = LocalContext.current
    val activity = context as? Activity
    var showAuthDialog by remember { mutableStateOf(false) }

    // Prevent rapid navigation
    var lastNavigationTime by remember { mutableStateOf(0L) }
    val navigationCooldown = 500L // 500ms cooldown between navigation calls

    fun safeNavigate(route: String) {
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastNavigationTime > navigationCooldown) {
            lastNavigationTime = currentTime
            navController.navigate(route)
        }
    }

    if (showAuthDialog) {
        AlertDialog(
            onDismissRequest = { showAuthDialog = false },
            title = { Text("Sign In Required", fontWeight = FontWeight.Bold) },
            text = { Text("Please sign in or sign up to play Gundu Ata and start winning!") },
            confirmButton = {
                TextButton(onClick = {
                    showAuthDialog = false
                    navController.navigate("login")
                }) {
                    Text("Sign In", color = PrimaryYellow, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = {
                    showAuthDialog = false
                    navController.navigate("signup")
                }) {
                    Text("Sign Up", fontWeight = FontWeight.Bold)
                }
            }
        )
    }

    fun launchGame() {
        try {
            // Check if user is logged in
            if (!viewModel.loginSuccess) {
                android.util.Log.w("AppNavigation", "User not logged in, showing auth dialog")
                showAuthDialog = true
                return
            }

            // Get authentication data
            val authToken = sessionManager.fetchAuthToken()
            val refreshToken = sessionManager.fetchRefreshToken()
            val username = sessionManager.fetchUsername()
            val userId = sessionManager.fetchUserId()

            // Verify token exists
            if (authToken == null || authToken.isEmpty()) {
                android.util.Log.e("AppNavigation", "Auth token is null or empty!")
                Toast.makeText(context, "Authentication error. Please login again.", Toast.LENGTH_LONG).show()
                return
            }

            android.util.Log.d("AppNavigation", "Launching Unity with auth - user: $username, userId: $userId, token: ${authToken.take(20)}...")

            // Sync auth to Unity PlayerPrefs BEFORE launching (this is critical)
            sessionManager.syncAuthToUnity()

            // Verify Unity PlayerPrefs were set
            try {
                val unityPrefsName = "${context.packageName}.v2.playerprefs"
                val unityPrefs = context.getSharedPreferences(unityPrefsName, android.content.Context.MODE_PRIVATE)
                val storedToken = unityPrefs.getString("auth_token", null)
                val isLoggedIn = unityPrefs.getString("is_logged_in", "false")
                android.util.Log.d("AppNavigation", "Unity PlayerPrefs verification - token exists: ${storedToken != null}, is_logged_in: $isLoggedIn")
            } catch (e: Exception) {
                android.util.Log.e("AppNavigation", "Failed to verify Unity PlayerPrefs", e)
            }

            // Launch Unity with Intent extras
            val intent = Intent(context, com.unity3d.player.UnityPlayerGameActivity::class.java)

            // Pass authentication data to Unity via Intent extras
            // Unity's UnityPlayerGameActivity reads from SharedPreferences first, then Intent extras
            // Make sure we use the exact keys Unity expects
            val password = sessionManager.fetchPassword()
            
            intent.putExtra("token", authToken) // Unity looks for "token" first in Intent
            intent.putExtra("auth_token", authToken) // Also pass as auth_token
            intent.putExtra("refresh_token", refreshToken)
            intent.putExtra("username", username)
            intent.putExtra("user_id", userId)
            if (password != null) {
                intent.putExtra("password", password) // Unity also looks for password
            }
            
            // Additional metadata
            intent.putExtra("base_url", "https://gunduata.online")
            intent.putExtra("api_url", "https://gunduata.online/api/")
            intent.putExtra("is_logged_in", true)
            intent.putExtra("auto_login", true)
            intent.putExtra("from_android_app", true)
            intent.putExtra("login_method", "android_app")
            intent.putExtra("auth_timestamp", System.currentTimeMillis())
            intent.putExtra("login_timestamp", System.currentTimeMillis())
            
            android.util.Log.d("AppNavigation", "Intent extras set - token: ${authToken?.take(10)}..., username: $username, userId: $userId")

            // Also store in Unity PlayerPrefs again (redundant but ensures it's there)
            try {
                val unityPrefsName = "${context.packageName}.v2.playerprefs"
                val unityPrefs = context.getSharedPreferences(unityPrefsName, android.content.Context.MODE_PRIVATE)
                
                // Don't clear - just update to ensure latest data
                unityPrefs.edit()
                    .putString("user_token", authToken)
                    .putString("auth_token", authToken)
                    .putString("bearer_token", authToken)
                    .putString("access_token", authToken)
                    .putString("token", authToken)
                    .putString("refresh_token", refreshToken)
                    .putString("username", username)
                    .putString("user_id", userId)
                    .putString("base_url", "https://gunduata.online")
                    .putString("api_url", "https://gunduata.online/api/")
                    .putString("is_logged_in", "true")
                    .putString("auto_login", "true")
                    .putString("from_android_app", "true")
                    .putString("login_method", "android_app")
                    .putLong("auth_timestamp", System.currentTimeMillis())
                    .putLong("login_timestamp", System.currentTimeMillis())
                    .remove("logout_requested")
                    .remove("logout_timestamp")
                    .apply()

                android.util.Log.d("AppNavigation", "Unity PlayerPrefs updated successfully")
            } catch (e: Exception) {
                android.util.Log.e("AppNavigation", "Failed to update Unity PlayerPrefs", e)
            }

            context.startActivity(intent)
            Toast.makeText(context, "🎲 Launching Gundu Ata Unity game...", Toast.LENGTH_SHORT).show()

        } catch (e: Exception) {
            Toast.makeText(context, "Unable to open game. Please try again later.", Toast.LENGTH_SHORT).show()
        }
    }
    
    // Handle redirect requests (e.g. from Unity balance click)
    LaunchedEffect(activity?.intent) {
        activity?.intent?.getStringExtra("redirect")?.let { route ->
            navController.navigate(route) {
                launchSingleTop = true
            }
            activity.intent.removeExtra("redirect")
        }
    }

    val startDestination = "home"
    
    NavHost(navController = navController, startDestination = startDestination) {
        composable("login") {
            LoginScreen(
                viewModel = viewModel,
                onLoginSuccess = { navController.navigate("home") },
                onNavigateToSignUp = { 
                    navController.navigate("signup") {
                        popUpTo("login") { inclusive = true }
                    }
                },
                onNavigateToForgotPassword = {
                    navController.navigate("forgot_password")
                }
            )
        }
        composable("forgot_password") {
            ForgotPasswordScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onSuccess = {
                    navController.navigate("login") {
                        popUpTo("forgot_password") { inclusive = true }
                    }
                }
            )
        }
        composable("signup?ref={ref}") { backStackEntry ->
            val refCode = backStackEntry.arguments?.getString("ref")
            SignUpScreen(
                viewModel = viewModel,
                initialReferralCode = refCode ?: "",
                onSignUpSuccess = { navController.navigate("home") },
                onNavigateToSignIn = { 
                    navController.navigate("login") {
                        popUpTo("signup") { inclusive = true }
                    }
                }
            )
        }
        composable("signup") {
            SignUpScreen(
                viewModel = viewModel,
                onSignUpSuccess = { navController.navigate("home") },
                onNavigateToSignIn = { 
                    navController.navigate("login") {
                        popUpTo("signup") { inclusive = true }
                    }
                }
            )
        }
        composable("home") {
            HomeScreen(
                viewModel = viewModel,
                onGameClick = { gameId ->
                    if (gameId == "gundu_ata") {
                        if (viewModel.loginSuccess) {
                            launchGame()
                        } else {
                            showAuthDialog = true
                        }
                    }
                },
                onNavigate = { route ->
                    if (route == "gundu_ata") {
                        if (viewModel.loginSuccess) {
                            launchGame()
                        } else {
                            showAuthDialog = true
                        }
                    } else if (route == "me") {
                        if (viewModel.loginSuccess) {
                            safeNavigate("me")
                        } else {
                            showAuthDialog = true
                        }
                    } else if (route != "home") {
                        safeNavigate(route)
                    }
                }
            )
        }
        composable("me") {
            ProfileScreen(
                viewModel = viewModel,
                onNavigate = { route ->
                    if (route == "gundu_ata") {
                        if (viewModel.loginSuccess) {
                            launchGame()
                        } else {
                            showAuthDialog = true
                        }
                    } else {
                        navController.navigate(route)
                    }
                }
            )
        }
        composable("wallet") {
            WalletScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onNavigateToDeposit = { navController.navigate("deposit") },
                onNavigateToWithdraw = { navController.navigate("withdraw") }
            )
        }
        composable("deposit") {
            DepositScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onNavigateToWithdraw = { navController.navigate("withdraw") },
                onNavigateToPayment = { amount, method ->
                    navController.navigate("payment/$amount/$method")
                }
            )
        }
        composable("payment/{amount}/{method}") { backStackEntry ->
            val amount = backStackEntry.arguments?.getString("amount") ?: "0"
            val method = backStackEntry.arguments?.getString("method") ?: "UPI"
            PaymentScreen(
                amount = amount,
                paymentMethod = method,
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onSubmitSuccess = {
                    navController.navigate("deposits_record") {
                        popUpTo("home") { inclusive = false }
                    }
                }
            )
        }
        composable("withdraw") {
            WithdrawScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onAddBankAccount = {
                    navController.navigate("add_bank_account")
                }
            )
        }
        composable("add_bank_account") {
            AddBankAccountScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onSubmitSuccess = {
                    navController.popBackStack()
                }
            )
        }
        composable("transactions") {
            TransactionHistoryScreen(
                title = "Transaction Record",
                initialCategory = "Deposit",
                showTabs = true,
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("deposits_record") {
            TransactionHistoryScreen(
                title = "Deposit Record",
                initialCategory = "Deposit",
                showTabs = false,
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("withdrawals_record") {
            TransactionHistoryScreen(
                title = "Withdrawal Record",
                initialCategory = "Withdraw",
                showTabs = false,
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("betting_record") {
            TransactionHistoryScreen(
                title = "Betting Record",
                initialCategory = "Betting",
                showTabs = false,
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("personal_info") {
            PersonalInfoScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("lucky_wheel") {
            LuckyWheelScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("lucky_draw") {
            LuckyDrawScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("withdrawal_account") {
            WithdrawalAccountScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onAddBankAccount = { navController.navigate("add_bank_account") }
            )
        }
        composable("security") {
            SecurityScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("info") {
            InfoScreen(
                onBack = { navController.popBackStack() }
            )
        }
        composable("affiliate") {
            AffiliateScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("help_center") {
            HelpCenterScreen(
                onBack = { navController.popBackStack() }
            )
        }
        composable("game_guidelines") {
            GameGuidelinesScreen(
                onBack = { navController.popBackStack() }
            )
        }
    }
}
