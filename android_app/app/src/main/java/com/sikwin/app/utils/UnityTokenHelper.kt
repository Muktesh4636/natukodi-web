package com.sikwin.app.utils

import android.content.Context
import android.content.Intent
import android.util.Log
import org.json.JSONObject

object UnityTokenHelper {
    private const val TAG = "UnityTokenHelper"

    /**
     * Send access and refresh tokens to Unity.
     */
    fun sendTokensToUnity(access: String, refresh: String) {
        // Disabled access token passing as requested
        Log.d(TAG, "sendTokensToUnity: Access token passing is currently disabled")
        return
    }

    /**
     * Sends tokens to Unity: direct UnitySendMessage + broadcast fallback.
     * Token-only: do NOT send username/password.
     */
    fun sendTokensToUnity(
        context: Context,
        access: String,
        refresh: String
    ) {
        try {
            // Avoid UnitySendMessage token injection; rely on prefs pre-write and broadcast.
            sendTokensToUnity(access, refresh)

            val intent = Intent("com.sikwin.app.TOKEN_UPDATE").apply {
                putExtra("access", access)
                putExtra("refresh", refresh)
                setPackage(context.packageName)
            }
            context.sendBroadcast(intent)
            Log.d(TAG, "Token broadcast sent")
        } catch (e: Exception) {
            Log.e(TAG, "Error sending token broadcast: ${e.message}")
        }
    }

    /**
     * Trigger logout in Unity using Broadcast.
     */
    fun sendLogoutToUnity(context: Context) {
        try {
            Log.d(TAG, "Sending logout to Unity via Broadcast")
            val intent = Intent("com.sikwin.app.TOKEN_UPDATE").apply {
                putExtra("action", "logout")
                setPackage(context.packageName)
            }
            context.sendBroadcast(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Error sending logout broadcast: ${e.message}")
        }
    }
}
