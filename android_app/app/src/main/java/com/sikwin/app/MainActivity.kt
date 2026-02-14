package com.sikwin.app

import android.os.Bundle
import android.content.Intent
import android.view.View
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.rememberNavController
import com.sikwin.app.data.api.RetrofitClient
import androidx.compose.ui.viewinterop.AndroidView
import com.sikwin.app.data.auth.SessionManager
import com.sikwin.app.navigation.AppNavigation
import com.sikwin.app.ui.theme.GunduAtaTheme
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel
import com.sikwin.app.ui.viewmodels.GunduAtaViewModelFactory

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val sessionManager = SessionManager(this)
        RetrofitClient.init(sessionManager)
        
        // Handle incoming logout request from Unity or other sources
        handleIntent(intent, sessionManager)
        
        setContent {
            GunduAtaTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()
                    val viewModel: GunduAtaViewModel = viewModel(
                        factory = GunduAtaViewModelFactory(sessionManager)
                    )
                    
                    // Listen for deep links or special intents
                    LaunchedEffect(intent) {
                        if (intent?.getStringExtra("action") == "logout") {
                            viewModel.logout()
                            navController.navigate("home") {
                                popUpTo(0) { inclusive = true }
                            }
                        }
                        
                        // Handle referral deep link: https://gunduata.com/signup?ref=CODE
                        intent?.data?.let { uri ->
                            if (uri.path == "/signup") {
                                val refCode = uri.getQueryParameter("ref")
                                if (!refCode.isNullOrBlank()) {
                                    navController.navigate("signup?ref=$refCode")
                                }
                            }
                        }
                    }

                    AppNavigation(
                        navController = navController, 
                        viewModel = viewModel,
                        sessionManager = sessionManager
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
    }

    override fun onPause() {
        super.onPause()
    }

    override fun onDestroy() {
        super.onDestroy()
        // We don't quit Unity here to keep it alive for next launch if needed, 
        // but if the app is truly being destroyed by the OS, we should clean up.
        // However, UnityPlayer.quit() usually kills the process.
    }

    override fun onNewIntent(intent: android.content.Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        // Session manager is recreated here but it's fine for clearing prefs
        handleIntent(intent, SessionManager(this))
    }

    private fun handleIntent(intent: android.content.Intent?, sessionManager: SessionManager) {
        if (intent?.getStringExtra("action") == "logout") {
            sessionManager.logout()
        }
    }
}
