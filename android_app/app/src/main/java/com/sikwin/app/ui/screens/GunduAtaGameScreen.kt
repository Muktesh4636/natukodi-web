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
import android.util.Log
import android.content.Intent
import com.unity3d.player.UnityPlayerGameActivity

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
        val username = sessionManager.fetchUsername()
        val password = sessionManager.fetchPassword()
        val intent = Intent(context, UnityPlayerGameActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (!token.isNullOrBlank()) {
                putExtra("token", token)
                putExtra("access_token", token)
                putExtra("auth_token", token)
            }
            if (!refresh.isNullOrBlank()) putExtra("refresh_token", refresh)
            if (!username.isNullOrBlank()) putExtra("username", username)
            if (!password.isNullOrBlank()) putExtra("password", password)
        }
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
