package com.sikwin.app.navigation

import android.app.Activity
import android.content.Intent
import android.net.Uri as AndroidUri
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
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.foundation.Image
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.Alignment

@Composable
fun AppNavigation(
    navController: NavHostController,
    viewModel: GunduAtaViewModel,
    sessionManager: SessionManager
) {
    val context = LocalContext.current
    val activity = context as? Activity
    var showAuthDialog by remember { mutableStateOf(false) }

    // App Update Check
    LaunchedEffect(Unit) {
        try {
            val packageInfo = context.packageManager.getPackageInfo(context.packageName, 0)
            val currentVersionCode = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
                packageInfo.longVersionCode.toInt()
            } else {
                @Suppress("DEPRECATION")
                packageInfo.versionCode
            }
            viewModel.checkForUpdates(currentVersionCode)
        } catch (e: Exception) {
            android.util.Log.e("AppNavigation", "Failed to get version code", e)
        }
    }

    if (viewModel.showUpdateDialog) {
        AlertDialog(
            onDismissRequest = { 
                if (!viewModel.isForceUpdate) {
                    viewModel.showUpdateDialog = false
                }
            },
            containerColor = com.sikwin.app.ui.theme.SurfaceColor,
            title = { 
                Text(
                    "New Update Available", 
                    fontWeight = FontWeight.Bold,
                    color = com.sikwin.app.ui.theme.TextWhite,
                    fontSize = 20.sp
                ) 
            },
            text = { 
                Column {
                    Text(
                        "A new version of Gundu Ata is available.",
                        color = com.sikwin.app.ui.theme.TextWhite,
                        fontSize = 16.sp
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    viewModel.latestVersionName?.let { 
                        Text(
                            "Version: $it", 
                            fontSize = 14.sp, 
                            color = com.sikwin.app.ui.theme.TextGrey
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        if (viewModel.isForceUpdate) {
                            "This update is required. Please update now to continue using the app."
                        } else {
                            "Please update to the latest version to continue enjoying the game and new features."
                        },
                        color = com.sikwin.app.ui.theme.TextWhite,
                        fontSize = 14.sp
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        viewModel.updateUrl?.let { url ->
                            try {
                                val intent = Intent(Intent.ACTION_VIEW, AndroidUri.parse(url))
                                context.startActivity(intent)
                                // If force update, don't close dialog - user must update
                                if (!viewModel.isForceUpdate) {
                                    viewModel.showUpdateDialog = false
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Could not open download link", Toast.LENGTH_SHORT).show()
                            }
                        } ?: run {
                            Toast.makeText(context, "Download URL not available", Toast.LENGTH_SHORT).show()
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryYellow),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        "Update Now", 
                        color = com.sikwin.app.ui.theme.BlackBackground, 
                        fontWeight = FontWeight.Bold
                    )
                }
            },
            dismissButton = if (!viewModel.isForceUpdate) {
                {
                    TextButton(
                        onClick = { viewModel.showUpdateDialog = false }
                    ) {
                        Text(
                            "Later",
                            color = com.sikwin.app.ui.theme.TextGrey
                        )
                    }
                }
            } else null
        )
    }

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
            title = { Text("Sign In Required", fontWeight = androidx.compose.ui.text.font.FontWeight.Bold) },
            text = { Text("Please sign in or sign up to play Gundu Ata and start winning!") },
            confirmButton = {
                TextButton(onClick = {
                    showAuthDialog = false
                    navController.navigate("login")
                }) {
                    Text("Sign In", color = PrimaryYellow, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = {
                    showAuthDialog = false
                    navController.navigate("signup")
                }) {
                    Text("Sign Up", fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
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

            // CRITICAL: Force a fresh timer fetch right before showing the loading screen
            viewModel.startTimerPreloading()

            // Show loading screen state
            navController.navigate("game_loading")
        } catch (e: Exception) {
            Toast.makeText(context, "Unable to open game. Please try again later.", Toast.LENGTH_SHORT).show()
        }
    }

    fun executeGameLaunch() {
        try {
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

            // Sync auth to Unity PlayerPrefs BEFORE launching
            sessionManager.syncAuthToUnity()

            // Launch Unity with Intent extras
            val intent = Intent(context, com.unity3d.player.UnityPlayerGameActivity::class.java)
            val password = sessionManager.fetchPassword()
            
            intent.putExtra("token", authToken)
            intent.putExtra("auth_token", authToken)
            intent.putExtra("refresh_token", refreshToken)
            intent.putExtra("username", username)
            intent.putExtra("user_id", userId)
            if (password != null) {
                intent.putExtra("password", password)
            }
            
            intent.putExtra("base_url", com.sikwin.app.utils.Constants.BASE_URL.removeSuffix("api/"))
            intent.putExtra("api_url", com.sikwin.app.utils.Constants.BASE_URL)
            intent.putExtra("is_logged_in", true)
            intent.putExtra("auto_login", true)
            intent.putExtra("from_android_app", true)
            intent.putExtra("login_method", "android_app")
            intent.putExtra("auth_timestamp", System.currentTimeMillis())
            intent.putExtra("login_timestamp", System.currentTimeMillis())
            
            // CRITICAL: Ensure we pass the ABSOLUTE LATEST timer data available
            // This prevents the "70 second freeze" which happens if old data is passed
            viewModel.preLoadedTimer?.let { 
                intent.putExtra("preloaded_timer", it) 
                android.util.Log.d("AppNavigation", "Passing FRESH timer to Unity: $it")
            }
            viewModel.preLoadedStatus?.let { intent.putExtra("preloaded_status", it) }
            viewModel.preLoadedRoundId?.let { intent.putExtra("preloaded_round_id", it) }
            intent.putExtra("preloaded_timestamp", System.currentTimeMillis())
            
            context.startActivity(intent)
        } catch (e: Exception) {
            android.util.Log.e("AppNavigation", "Final launch failed", e)
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
        composable("signup?ref={ref}&spin={spin}") { backStackEntry ->
            val refCode = backStackEntry.arguments?.getString("ref")
            val spinBalance = backStackEntry.arguments?.getString("spin")?.toIntOrNull() ?: 0
            SignUpScreen(
                viewModel = viewModel,
                initialReferralCode = refCode ?: "",
                initialSpinBalance = spinBalance,
                onSignUpSuccess = { navController.navigate("home") },
                onNavigateToSignIn = { 
                    navController.navigate("login") {
                        popUpTo("signup") { inclusive = true }
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
                            navController.navigate("me") {
                                // Pop up to home to avoid backstack issues
                                popUpTo("home") { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        } else {
                            showAuthDialog = true
                        }
                    } else if (route == "wallet" || route == "deposit" || route == "withdraw" || route == "transactions") {
                        if (viewModel.loginSuccess) {
                            safeNavigate(route)
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
                    } else if (route == "home") {
                        navController.navigate("home") {
                            popUpTo("home") { inclusive = true }
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
                onBack = { navController.popBackStack() },
                onNavigate = { route -> navController.navigate(route) }
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
        composable("game_loading") {
            GameLoadingScreen(
                onLoadingComplete = { 
                    executeGameLaunch()
                    navController.popBackStack()
                }
            )
        }
    }
}

@Composable
fun GameLoadingScreen(onLoadingComplete: () -> Unit) {
    var progress by remember { mutableStateOf(0f) }
    
    LaunchedEffect(Unit) {
        val duration = 7000L // 7 seconds
        val interval = 50L
        val steps = duration / interval
        
        for (i in 1..steps) {
            delay(interval)
            progress = i.toFloat() / steps
        }
        onLoadingComplete()
    }

    Box(
        modifier = androidx.compose.ui.Modifier
            .fillMaxSize()
            .background(com.sikwin.app.ui.theme.BlackBackground),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Image(
                painter = painterResource(id = com.sikwin.app.R.drawable.app_logo),
                contentDescription = null,
                modifier = androidx.compose.ui.Modifier
                    .size(120.dp)
                    .clip(RoundedCornerShape(16.dp))
            )
            Spacer(modifier = androidx.compose.ui.Modifier.height(24.dp))
            Text(
                text = "Gundu Ata",
                color = com.sikwin.app.ui.theme.TextWhite,
                fontSize = 32.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
            )
            Spacer(modifier = androidx.compose.ui.Modifier.height(48.dp))
            CircularProgressIndicator(
                progress = { progress },
                color = com.sikwin.app.ui.theme.PrimaryYellow,
                strokeWidth = 4.dp,
                modifier = androidx.compose.ui.Modifier.size(64.dp)
            )
            Spacer(modifier = androidx.compose.ui.Modifier.height(16.dp))
            Text(
                text = "Loading game assets...",
                color = com.sikwin.app.ui.theme.TextGrey,
                fontSize = 16.sp
            )
        }
    }
}
