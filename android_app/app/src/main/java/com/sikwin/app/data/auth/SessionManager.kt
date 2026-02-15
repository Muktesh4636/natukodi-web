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
        // Store in both formats for compatibility
        // Unity expects "auth_token" but we also keep "user_token" for our app
        prefs.edit()
            .putString(USER_TOKEN, token)
            .putString("auth_token", token) // Unity reads this key
            .apply()
    }

    fun fetchAuthToken(): String? {
        // Try both keys for compatibility
        val token = prefs.getString(USER_TOKEN, null) ?: prefs.getString("auth_token", null)
        
        // Migration: If we have user_token but not auth_token, copy it
        if (token != null && prefs.contains(USER_TOKEN) && !prefs.contains("auth_token")) {
            prefs.edit().putString("auth_token", token).apply()
            android.util.Log.d("SessionManager", "Migrated user_token to auth_token for Unity compatibility")
        }
        
        return token
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
        return prefs.getString(USERNAME, null)
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

    fun syncAuthToUnity() {
        // Sync authentication data to Unity PlayerPrefs for seamless login
        try {
            val unityPrefsName = "${context.packageName}.v2.playerprefs"
            val unityPrefs = context.getSharedPreferences(unityPrefsName, Context.MODE_PRIVATE)
            
            val authToken = fetchAuthToken()
            val username = fetchUsername()
            val userId = fetchUserId()
            
            if (authToken != null) {
                unityPrefs.edit()
                    .putString("user_token", authToken)
                    .putString("auth_token", authToken)
                    .putString("bearer_token", authToken)
                    .putString("username", username)
                    .putString("user_id", userId)
                    .putString("base_url", com.sikwin.app.utils.Constants.BASE_URL.removeSuffix("api/"))
                    .putString("api_url", com.sikwin.app.utils.Constants.BASE_URL)
                    .putString("is_logged_in", "true")
                    .putString("auto_login", "true")
                    .putString("from_android_app", "true")
                    .putString("login_method", "android_app")
                    .putLong("auth_timestamp", System.currentTimeMillis())
                    .putLong("login_timestamp", System.currentTimeMillis())
                    .remove("logout_requested")
                    .remove("logout_timestamp")
                    .apply()
                
                android.util.Log.d("SessionManager", "Synced auth data to Unity PlayerPrefs")
            }
        } catch (e: Exception) {
            android.util.Log.e("SessionManager", "Failed to sync auth to Unity", e)
        }
    }
    
    fun logout() {
        // Clear Kotlin/Android prefs
        prefs.edit().clear().apply()
        
        // Clear Unity PlayerPrefs to sync logout
        try {
            val unityPrefsName = "${context.packageName}.v2.playerprefs"
            val unityPrefs = context.getSharedPreferences(unityPrefsName, Context.MODE_PRIVATE)
            
            // Set logout flags for Unity
            unityPrefs.edit()
                .clear()
                .putString("is_logged_in", "false")
                .putString("logout_requested", "true")
                .putLong("logout_timestamp", System.currentTimeMillis())
                .apply()
            
            android.util.Log.d("SessionManager", "Cleared Unity PlayerPrefs and set logout flags")
        } catch (e: Exception) {
            android.util.Log.e("SessionManager", "Failed to clear Unity prefs", e)
        }
    }

    fun isNewUser(): Boolean {
        return prefs.getBoolean("is_new_user", true)
    }

    fun setNewUser(isNew: Boolean) {
        prefs.edit().putBoolean("is_new_user", isNew).apply()
    }

    fun getContext(): Context = context
}
