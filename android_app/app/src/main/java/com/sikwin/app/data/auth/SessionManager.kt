package com.sikwin.app.data.auth

import android.content.Context
import android.content.SharedPreferences

class SessionManager(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("gunduata_prefs", Context.MODE_PRIVATE)

    companion object {
        private const val USER_TOKEN = "user_token"
        private const val REFRESH_TOKEN = "refresh_token"
        private const val USERNAME = "username"
        private const val USER_ID = "user_id"
        private const val USER_PASS = "user_pass"
    }

    fun saveAuthToken(token: String) {
        prefs.edit().putString(USER_TOKEN, token).apply()
    }

    fun fetchAuthToken(): String? {
        return prefs.getString(USER_TOKEN, null)
    }

    fun saveRefreshToken(token: String) {
        prefs.edit().putString(REFRESH_TOKEN, token).apply()
    }

    fun fetchRefreshToken(): String? {
        return prefs.getString(REFRESH_TOKEN, null)
    }

    fun saveUsername(username: String) {
        prefs.edit().putString(USERNAME, username).apply()
    }

    fun fetchUsername(): String? {
        return prefs.getString(USERNAME, "User")
    }

    fun saveUserId(userId: Int) {
        prefs.edit().putInt(USER_ID, userId).apply()
    }

    fun fetchUserId(): String {
        return prefs.getInt(USER_ID, 0).toString()
    }

    fun savePassword(password: String) {
        prefs.edit().putString(USER_PASS, password).apply()
    }

    fun fetchPassword(): String? {
        return prefs.getString(USER_PASS, null)
    }

    fun logout() {
        // Clear Kotlin/Android prefs
        prefs.edit().clear().apply()
        
        // Clear Unity PlayerPrefs to sync logout
        try {
            val unityPrefsName = "${context.packageName}.v2.playerprefs"
            val unityPrefs = context.getSharedPreferences(unityPrefsName, Context.MODE_PRIVATE)
            unityPrefs.edit().clear().apply()
            android.util.Log.d("SessionManager", "Cleared Unity PlayerPrefs ($unityPrefsName)")
        } catch (e: Exception) {
            android.util.Log.e("SessionManager", "Failed to clear Unity prefs", e)
        }
    }
}
