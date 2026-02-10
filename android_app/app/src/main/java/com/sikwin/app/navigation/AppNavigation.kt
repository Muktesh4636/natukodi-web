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
// import com.unity3d.player.UnityPlayerGameActivity
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
                showAuthDialog = true
                return
            }

            // Show message that Unity game is coming soon
            Toast.makeText(
                context,
                "🎲 Unity game launching soon! Opening web version for now...",
                Toast.LENGTH_LONG
            ).show()

            // For now, open web version until Unity integration is complete
            val gameUrl = "https://gunduata.online/" // Production game URL
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(gameUrl))
            context.startActivity(intent)

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
                onNavigateToPayment = { amount ->
                    navController.navigate("payment/$amount")
                }
            )
        }
        composable("payment/{amount}") { backStackEntry ->
            val amount = backStackEntry.arguments?.getString("amount") ?: "0"
            PaymentScreen(
                amount = amount,
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
    }
}
