package com.sikwin.app.ui.screens

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.sikwin.app.R
import com.sikwin.app.data.auth.SessionManager
import com.sikwin.app.ui.viewmodels.GunduAtaViewModel
import com.sikwin.app.utils.UnityTokenHelper
import android.util.Log
import android.content.Intent
import com.unity3d.player.UnityPlayerGameActivity
import com.unity3d.player.UnityTokenHolder

@Composable
fun GunduAtaGameScreen(
    viewModel: GunduAtaViewModel,
    sessionManager: SessionManager,
    onBack: () -> Unit
) {
    val context = LocalContext.current

    // Unity's Java classes are obfuscated and vary between exports, so embedding a Unity view
    // directly inside Compose is brittle. We launch the stable Unity host Activity instead.
    LaunchedEffect(Unit) {
        Log.d("GunduAtaGameScreen", "Launching UnityPlayerGameActivity")
        sessionManager.syncAuthToUnity()

        val token = sessionManager.fetchAuthToken()
        val refresh = sessionManager.fetchRefreshToken()
        val intent = Intent(context, UnityPlayerGameActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (!token.isNullOrBlank()) {
                putExtra("token", token)
                putExtra("auth_token", token)
                putExtra("access_token", token)
                putExtra("access", token)
            }
            if (!refresh.isNullOrBlank()) {
                putExtra("refresh_token", refresh)
                putExtra("refresh", refresh)
            }
        }
        Log.d(
            "GunduAtaGameScreen",
            "Launching Unity with token=${if (token.isNullOrBlank()) "EMPTY" else "present"}, refresh=${if (refresh.isNullOrBlank()) "EMPTY" else "present"}"
        )
        com.unity3d.player.UnityTokenHolder.setTokens(token ?: "", refresh ?: "", "", "")
        context.startActivity(intent)
    }

    Box(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Button(
            onClick = {
                Log.d("GunduAtaGameScreen", "User requested back from game launcher screen")
                onBack()
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(stringResource(R.string.back))
        }
    }
}
