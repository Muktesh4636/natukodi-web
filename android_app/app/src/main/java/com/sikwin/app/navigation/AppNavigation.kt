package com.sikwin.app.navigation

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri as AndroidUri
import android.widget.Toast
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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.Alignment
import androidx.compose.ui.res.stringResource
import com.sikwin.app.utils.Constants
import com.unity3d.player.UnityTokenHolder
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ProcessLifecycleOwner

@Composable
fun AppNavigation(
    navController: NavHostController,
    viewModel: GunduAtaViewModel,
    sessionManager: SessionManager
) {
    val context = LocalContext.current
    val activity = context as? Activity
    var showAuthDialog by remember { mutableStateOf(false) }

    // When app goes to background, set flag so support popup shows on next home visit (after reopen)
    DisposableEffect(Unit) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                viewModel.showSupportPopupOnNextHomeVisit = true
            }
        }
        ProcessLifecycleOwner.get().lifecycle.addObserver(observer)
        onDispose {
            ProcessLifecycleOwner.get().lifecycle.removeObserver(observer)
        }
    }

    // Register FCM token when user is logged in (for push notifications)
    LaunchedEffect(Unit) {
        if (sessionManager.fetchAuthToken() != null) {
            viewModel.registerFcmTokenIfNeeded()
        }
    }

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
    var lastGameLaunchTime by remember { mutableStateOf(0L) }
    val navigationCooldown = 500L // 500ms cooldown between navigation calls
    val gameLaunchCooldown = 1500L // Prevent double-tap crash when launching Unity

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
            title = { Text(stringResource(com.sikwin.app.R.string.sign_in_required), fontWeight = androidx.compose.ui.text.font.FontWeight.Bold) },
            text = { Text(stringResource(com.sikwin.app.R.string.sign_in_required_message)) },
            confirmButton = {
                TextButton(onClick = {
                    showAuthDialog = false
                    navController.navigate("login")
                }) {
                    Text(stringResource(com.sikwin.app.R.string.sign_in), color = PrimaryYellow, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = {
                    showAuthDialog = false
                    navController.navigate("signup")
                }) {
                    Text(stringResource(com.sikwin.app.R.string.sign_up), fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                }
            }
        )
    }

    // When user is logged out, show sign-in page (login/register); do not show balance
    LaunchedEffect(Unit) {
        if (sessionManager.fetchAuthToken().isNullOrBlank()) {
            navController.navigate("login") {
                popUpTo(0) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    fun executeGameLaunch() {
        val now = System.currentTimeMillis()
        if (now - lastGameLaunchTime < gameLaunchCooldown) return
        lastGameLaunchTime = now
        
        try {
            val authToken = sessionManager.fetchAuthToken()
            val refreshToken = sessionManager.fetchRefreshToken()
            android.util.Log.d("AppNavigation", "executeGameLaunch: token=${if (authToken.isNullOrBlank()) "EMPTY" else "${authToken.take(8)}..."}, refresh=${if (refreshToken.isNullOrBlank()) "EMPTY" else "${refreshToken.take(8)}..."}")
            val userId = sessionManager.fetchUserId()
            val isLoggedIn = !authToken.isNullOrBlank()

            // Launch embedded Unity activity from the same APK (single-app flow).
            val intent = Intent().setClassName(
                context.packageName,
                "com.unity3d.player.UnityPlayerGameActivity"
            )

            // Pass auth/session details (if available) for auto-login.
            intent.putExtra("token", authToken ?: "")
            intent.putExtra("auth_token", authToken ?: "")
            intent.putExtra("access_token", authToken ?: "")
            intent.putExtra("bearer_token", authToken ?: "")
            intent.putExtra("refresh_token", refreshToken ?: "")
            intent.putExtra("access", authToken ?: "")
            intent.putExtra("refresh", refreshToken ?: "")
            intent.putExtra("user_id", userId)
            
            intent.putExtra("base_url", Constants.BASE_URL.removeSuffix("api/"))
            intent.putExtra("api_url", Constants.BASE_URL)
            intent.putExtra("is_logged_in", isLoggedIn)
            intent.putExtra("auto_login", true)
            intent.putExtra("from_android_app", true)
            intent.putExtra("guest_mode", !isLoggedIn)
            intent.putExtra("login_method", "android_app")
            intent.putExtra("auth_timestamp", System.currentTimeMillis())
            intent.putExtra("login_timestamp", System.currentTimeMillis())
            
            intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            
            // Pass tokens for auto-login in standalone app (duplicate for safety)
            intent.putExtra("token", authToken ?: "")
            intent.putExtra("auth_token", authToken ?: "")
            intent.putExtra("access", authToken ?: "")
            intent.putExtra("refresh", refreshToken ?: "")

            // CRITICAL: Ensure we pass the ABSOLUTE LATEST timer data available
            // This prevents the "70 second freeze" which happens if old data is passed
            viewModel.preLoadedTimer?.let { 
                intent.putExtra("preloaded_timer", it) 
                android.util.Log.d("AppNavigation", "Passing FRESH timer to Unity: $it")
            }
            viewModel.preLoadedStatus?.let { intent.putExtra("preloaded_status", it) }
            viewModel.preLoadedRoundId?.let { intent.putExtra("preloaded_round_id", it) }
            intent.putExtra("preloaded_timestamp", System.currentTimeMillis())
            
            // CRITICAL: Sync auth to Unity PlayerPrefs BEFORE launch so GameManager.Start can read it
            sessionManager.syncAuthToUnity()

            // Store tokens (+ saved credentials) in static holder so Unity can read even if Intent is lost
            val savedUser = sessionManager.fetchUsername() ?: ""
            val savedPass = sessionManager.fetchPassword() ?: ""
            com.unity3d.player.UnityTokenHolder.setTokens(authToken ?: "", refreshToken ?: "", savedUser, savedPass)

            context.startActivity(intent)
        } catch (e: Exception) {
            android.util.Log.e("AppNavigation", "Final launch failed", e)
        }
    }

    fun launchGame() {
        try {
            executeGameLaunch()
        } catch (e: Exception) {
            android.util.Log.e("AppNavigation", "Launch failed", e)
            Toast.makeText(context, "Unable to open game. Please try again later.", Toast.LENGTH_SHORT).show()
        }
    }
    
    // Handle redirect requests (e.g. from Unity back button, balance click, dice results click)
    LaunchedEffect(activity?.intent) {
        val redirectRoute = activity?.intent?.getStringExtra("redirect")
        if (redirectRoute != null) {
            if (redirectRoute == "home") {
                navController.navigate("home") {
                    popUpTo("home") { inclusive = true }
                    launchSingleTop = true
                }
            } else {
                navController.navigate(redirectRoute) {
                    launchSingleTop = true
                }
            }
            activity.intent.removeExtra("redirect")
        }
    }

    val startDestination = "home"
    
    NavHost(navController = navController, startDestination = startDestination) {
        composable("gundu_ata_game") {
            GunduAtaGameScreen(
                viewModel = viewModel,
                sessionManager = sessionManager,
                onBack = { navController.popBackStack() }
            )
        }
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
                        if (!viewModel.loginSuccess) {
                            showAuthDialog = true
                        } else {
                            viewModel.syncAuthToUnity()
                            executeGameLaunch()
                        }
                    }
                },
                onNavigate = { route ->
                    if (route == "gundu_ata") {
                        if (!viewModel.loginSuccess) {
                            showAuthDialog = true
                        } else {
                            viewModel.syncAuthToUnity()
                            executeGameLaunch()
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
                    } else if (route.startsWith("wallet") || route.startsWith("deposit") || route.startsWith("withdraw") || route.startsWith("transactions")) {
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
                sessionManager = sessionManager,
                onNavigate = { route ->
                    if (route == "gundu_ata") {
                        if (!viewModel.loginSuccess) {
                            showAuthDialog = true
                        } else {
                            viewModel.syncAuthToUnity()
                            executeGameLaunch()
                        }
                    } else if (route == "home") {
                        navController.navigate("home") {
                            popUpTo("home") { inclusive = true }
                        }
                    } else if (route == "login") {
                        // After logout: go to sign-in and clear stack so user sees login/register (no balance)
                        navController.navigate("login") {
                            popUpTo(0) { inclusive = true }
                            launchSingleTop = true
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
        composable("deposit?method={method}") { backStackEntry ->
            val method = backStackEntry.arguments?.getString("method")
            DepositScreen(
                viewModel = viewModel,
                initialMethod = method,
                onBack = { navController.popBackStack() },
                onNavigateToWithdraw = { navController.navigate("withdraw") },
                onNavigateToPayment = { amount, paymentMethod ->
                    navController.navigate("payment/$amount/$paymentMethod")
                }
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
        composable("leaderboard") {
            LeaderboardScreen(
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
        composable("dice_results") {
            DiceResultsScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }
        composable("help_center") {
            HelpCenterScreen(
                onBack = { navController.popBackStack() }
            )
        }
        composable("languages") {
            LanguageScreen(
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
