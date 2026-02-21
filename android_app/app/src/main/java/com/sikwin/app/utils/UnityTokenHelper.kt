package com.sikwin.app.utils

import android.content.Context
import android.content.Intent
import android.util.Log
import com.unity3d.player.UnityPlayer
import org.json.JSONObject

object UnityTokenHelper {
    private const val TAG = "UnityTokenHelper"

    /**
     * Directly inject access/refresh tokens into Unity via UnitySendMessage.
     */
    fun sendTokensToUnity(access: String, refresh: String) {
        try {
            val json = JSONObject().apply {
                put("access", access)
                put("refresh", refresh)
            }.toString()

            UnityPlayer.UnitySendMessage(
                "GameManager",
                "SetAccessAndRefreshTokens",
                json
            )
            Log.d(TAG, "Tokens sent to Unity via UnitySendMessage")
        } catch (e: Exception) {
            Log.e(TAG, "Error sending tokens via UnitySendMessage: ${e.message}")
        }
    }

    /**
     * Sends tokens to Unity: direct UnitySendMessage first, then broadcast fallback
     * for cases where Unity isn't ready yet.
     */
    fun sendTokensToUnity(
        context: Context,
        access: String,
        refresh: String,
        username: String? = null
    ) {
        try {
            sendTokensToUnity(access, refresh)

            val intent = Intent("com.sikwin.app.TOKEN_UPDATE").apply {
                putExtra("access", access)
                putExtra("refresh", refresh)
                putExtra("username", username ?: "")
                setPackage(context.packageName)
            }
            context.sendBroadcast(intent)
            Log.d(TAG, "Token broadcast fallback sent")
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
