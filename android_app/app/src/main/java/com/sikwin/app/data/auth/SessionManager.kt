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
        private const val REFERRAL_CODE = "referral_code"
    }

    fun saveReferralCode(code: String?) {
        if (code != null) {
            prefs.edit().putString(REFERRAL_CODE, code).apply()
        }
    }

    fun fetchReferralCode(): String? {
        return prefs.getString(REFERRAL_CODE, null)
    }

    fun saveAuthToken(token: String) {
        // Store in both formats for compatibility
        // Unity expects "auth_token" but we also keep "user_token" for our app
        prefs.edit()
            .putString(USER_TOKEN, token)
            .putString("auth_token", token) // Unity reads this key
            .putString("access_token", token)
            .putString("access", token)
            .apply()
            
        // Sync to Unity PlayerPrefs immediately
        try {
            syncAuthToUnity()
        } catch (e: Exception) {
            android.util.Log.e("SessionManager", "Immediate sync failed", e)
        }
    }

    fun fetchAuthToken(): String? {
        // Try multiple keys for compatibility
        val token = prefs.getString(USER_TOKEN, null) 
            ?: prefs.getString("auth_token", null)
            ?: prefs.getString("access_token", null)
            ?: prefs.getString("access", null)
        
        // Migration: If we have user_token but not auth_token, copy it
        if (token != null && !prefs.contains("auth_token")) {
            prefs.edit()
                .putString("auth_token", token)
                .putString("access_token", token)
                .putString("access", token)
                .apply()
            android.util.Log.d("SessionManager", "Migrated token keys for Unity compatibility")
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
            // Standalone Unity app package name
            val standalonePackageName = "com.company.dicegame"
            
            // Unity stores its PlayerPrefs in a SharedPreferences file named [PACKAGE_NAME].v2.playerprefs
            val unityPrefsName = "$standalonePackageName.v2.playerprefs"
            
            val authToken = fetchAuthToken()
            val username = fetchUsername()
            val userId = fetchUserId()
            
            if (authToken != null) {
                android.util.Log.d("SessionManager", "Syncing auth data to Unity PlayerPrefs for $standalonePackageName")
                
                // 1. Write to the primary Unity PlayerPrefs file in the SAME process
                // Since Unity is part of the same APK (unityLibrary), it shares the same data directory.
                // We don't need to use createPackageContext if it's the same app.
                val targetPrefs = context.getSharedPreferences(unityPrefsName, Context.MODE_PRIVATE)

                targetPrefs.edit()
                    .putString("user_token", authToken)
                    .putString("auth_token", authToken)
                    .putString("bearer_token", authToken)
                    .putString("access_token", authToken)
                    .putString("access", authToken)
                    .putString("username", username)
                    .putString("user_id", userId)
                    .putString("base_url", "https://gunduata.online/")
                    .putString("api_url", "https://gunduata.online/api/")
                    .putString("is_logged_in", "true")
                    .putString("auto_login", "true")
                    .putString("from_android_app", "true")
                    .putString("login_method", "android_app")
                    .putLong("auth_timestamp", System.currentTimeMillis())
                    .putLong("login_timestamp", System.currentTimeMillis())
                    .remove("logout_requested")
                    .remove("logout_timestamp")
                    .apply()
                
                // 2. Also write to the "UnityPlayerPrefs" file which is common in some Unity versions
                val altPrefs = context.getSharedPreferences("UnityPlayerPrefs", Context.MODE_PRIVATE)
                
                altPrefs.edit()
                    .putString("auth_token", authToken)
                    .putString("access_token", authToken)
                    .putString("is_logged_in", "true")
                    .apply()

                // 3. Write to the "dicegame.v2.playerprefs" just in case package name is different
                try {
                    val fallbackPrefs = context.getSharedPreferences("dicegame.v2.playerprefs", Context.MODE_PRIVATE)
                    fallbackPrefs.edit()
                        .putString("auth_token", authToken)
                        .putString("is_logged_in", "true")
                        .apply()
                } catch (e: Exception) {}
                
                // 4. CRITICAL: Also write to the default SharedPreferences that Unity might check
                val defaultPrefs = context.getSharedPreferences("${context.packageName}_preferences", Context.MODE_PRIVATE)
                defaultPrefs.edit()
                    .putString("auth_token", authToken)
                    .putString("is_logged_in", "true")
                    .apply()

                // 5. NEW: Write to the Unity process specific SharedPreferences
                // Some Unity versions use the package name as the file name
                val processPrefs = context.getSharedPreferences("com.company.dicegame", Context.MODE_PRIVATE)
                processPrefs.edit()
                    .putString("auth_token", authToken)
                    .putString("is_logged_in", "true")
                    .apply()
            }
        } catch (e: Exception) {
            android.util.Log.e("SessionManager", "Failed to sync auth to Unity", e)
        }
    }

    fun syncAuthToUnityV2() {
        // Alternative sync for newer Android versions using a common prefix
        try {
            val standalonePackageName = "com.company.dicegame"
            val authToken = fetchAuthToken()
            if (authToken == null) return

            // Some Unity versions use this format
            val altPrefsName = "UnityPlayerPrefs"
            val altPrefs = context.getSharedPreferences(altPrefsName, Context.MODE_PRIVATE)
            altPrefs.edit()
                .putString("auth_token", authToken)
                .putString("is_logged_in", "true")
                .apply()
        } catch (e: Exception) {}
    }
    
    fun logout() {
        // Clear Kotlin/Android prefs
        prefs.edit().clear().apply()
        
        // Clear Unity PlayerPrefs to sync logout
        try {
            val standalonePackageName = "com.company.dicegame"
            val unityPrefsName = "$standalonePackageName.v2.playerprefs"
            
            val unityContext = try {
                context.createPackageContext(standalonePackageName, android.content.Context.CONTEXT_IGNORE_SECURITY)
            } catch (e: Exception) {
                null
            }

            // Clear primary prefs
            val targetPrefs = if (unityContext != null) {
                unityContext.getSharedPreferences(unityPrefsName, Context.MODE_PRIVATE)
            } else {
                context.getSharedPreferences(unityPrefsName, Context.MODE_PRIVATE)
            }
            
            targetPrefs.edit()
                .clear()
                .putString("is_logged_in", "false")
                .putString("logout_requested", "true")
                .putLong("logout_timestamp", System.currentTimeMillis())
                .apply()

            // Clear alt prefs
            val altPrefs = if (unityContext != null) {
                unityContext.getSharedPreferences("UnityPlayerPrefs", Context.MODE_PRIVATE)
            } else {
                context.getSharedPreferences("UnityPlayerPrefs", Context.MODE_PRIVATE)
            }
            altPrefs.edit().clear().apply()
            
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
