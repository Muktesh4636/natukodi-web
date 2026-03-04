package com.sikwin.app.data.auth

import android.content.Context
import android.content.SharedPreferences
import android.content.Intent
import com.unity3d.player.UnityTokenHolder

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
            .putString("is_logged_in", "true")
            // commit() avoids race where Unity launches before apply() is persisted
            .commit()
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
        // Store under multiple keys for backward/Unity compatibility.
        prefs.edit()
            .putString(REFRESH_TOKEN, token)
            .putString("refresh", token)
            .putString("refreshToken", token)
            .putString("is_logged_in", "true")
            .commit()
    }

    /**
     * Save access+refresh together and sync Unity once (prevents login→open-game timing races).
     */
    fun saveTokens(access: String, refresh: String) {
        prefs.edit()
            .putString(USER_TOKEN, access)
            .putString("auth_token", access)
            .putString("access_token", access)
            .putString("access", access)
            .putString(REFRESH_TOKEN, refresh)
            .putString("refresh", refresh)
            .putString("refreshToken", refresh)
            .putString("is_logged_in", "true")
            .commit()

        try {
            syncAuthToUnity()
        } catch (e: Exception) {
            android.util.Log.e("SessionManager", "saveTokens syncAuthToUnity failed", e)
        }
    }

    fun fetchRefreshToken(): String? {
        val t = prefs.getString(REFRESH_TOKEN, null)
            ?: prefs.getString("refresh", null)
            ?: prefs.getString("refreshToken", null)

        // Migration: if refresh exists under an old key, copy it to the canonical one.
        if (!t.isNullOrBlank() && !prefs.contains(REFRESH_TOKEN)) {
            prefs.edit().putString(REFRESH_TOKEN, t).apply()
        }
        return t
    }

    fun saveUsername(username: String) {
        prefs.edit()
            .putString(USERNAME, username)
            .putString("USERNAME_KEY", username)
            .putString("UserName", username)
            .apply()
    }

    fun fetchUsername(): String? {
        return prefs.getString(USERNAME, null)
    }

    fun saveUserId(userId: Int) {
        prefs.edit().putString(USER_ID, userId.toString()).apply()
    }

    fun fetchUserId(): String {
        return try {
            prefs.getString(USER_ID, "0") ?: "0"
        } catch (e: ClassCastException) {
            // Fallback if it was accidentally stored as an int
            prefs.getInt(USER_ID, 0).toString()
        }
    }

    fun savePassword(password: String) {
        prefs.edit()
            .putString(USER_PASS, password)
            .putString("PASSWORD_KEY", password)
            .putString("Password", password)
            .apply()
    }

    fun fetchPassword(): String? {
        return prefs.getString(USER_PASS, null)
    }

    fun clearSavedPassword() {
        prefs.edit().remove(USER_PASS).apply()
    }

    fun syncAuthToUnity() {
        // Sync authentication data to Unity PlayerPrefs for seamless login
        try {
            // Comprehensive list of all possible SharedPreferences files Unity might check
            val standalonePackageName = "com.company.dicegame"
            val pkg = context.packageName
            
            val authToken = fetchAuthToken()
            val refreshToken = fetchRefreshToken()
            val userId = fetchUserId()
            val username = fetchUsername()
            val password = fetchPassword()
            
            // CRITICAL: Always push to the static holder FIRST.
            // This is the fastest way for Unity to see the tokens in Awake().
            if (!authToken.isNullOrBlank()) {
                com.unity3d.player.UnityTokenHolder.setTokens(
                    authToken,
                    refreshToken ?: "",
                    username ?: "",
                    password ?: ""
                )
                android.util.Log.d(
                    "SessionManager",
                    "syncAuthToUnity: Set static UnityTokenHolder (accessLen=${authToken.length}, user=${username ?: ""})"
                )
            }

            // Comprehensive list of all possible SharedPreferences files Unity might check
            val allPrefsToSync = arrayOf(
                "$standalonePackageName.v2.playerprefs",
                "$pkg.v2.playerprefs",
                "gunduata_prefs",
                "UnityPlayerPrefs",
                "dicegame.v2.playerprefs",
                "PlayerPrefs",
                "${pkg}_preferences",
                standalonePackageName,
                pkg,
                "${pkg}.playerprefs"
            )

            for (prefName in allPrefsToSync) {
                context.getSharedPreferences(prefName, Context.MODE_PRIVATE).edit().also { e ->
                    // Sync tokens only
                    if (!authToken.isNullOrBlank()) {
                        e.putString("auth_token", authToken)
                        e.putString("access_token", authToken)
                        e.putString("access", authToken)
                        e.putString("user_token", authToken)
                        e.putString("token", authToken)
                        e.putString("bearer_token", authToken)
                    }
                    
                    if (!refreshToken.isNullOrBlank()) {
                        e.putString("refresh_token", refreshToken)
                        e.putString("refresh", refreshToken)
                        e.putString("refreshToken", refreshToken)
                    }

                    // Sync login credentials to Unity (for auto-fill/auto-login inside Unity).
                    // If you don't want to persist password, call savePassword(..., savePassword=false) in Kotlin.
                    if (!username.isNullOrBlank()) {
                        e.putString("username", username)
                        e.putString("USERNAME_KEY", username)
                        e.putString("UserName", username)
                    } else {
                        e.remove("username")
                        e.remove("USERNAME_KEY")
                        e.remove("UserName")
                    }
                    if (!password.isNullOrBlank()) {
                        e.putString("password", password)
                        e.putString("PASSWORD_KEY", password)
                        e.putString("Password", password)
                        e.putString("user_pass", password)
                    } else {
                        e.remove("password")
                        e.remove("PASSWORD_KEY")
                        e.remove("Password")
                        e.remove("user_pass")
                    }
                    
                    e.putString("user_id", userId)
                    e.putString("is_logged_in", "true")
                    e.remove("logout_requested");
                    e.remove("logout_timestamp");
                    e.commit();
                }
            }
            
            // 10. BROADCAST: Send a broadcast that UnityPlayerGameActivity can catch
            if (!authToken.isNullOrBlank()) {
                val intent = Intent("com.sikwin.app.TOKEN_UPDATE")
                intent.putExtra("access", authToken)
                intent.putExtra("refresh", refreshToken ?: "")
                intent.setPackage(context.packageName)
                context.sendBroadcast(intent)
                android.util.Log.d("SessionManager", "Sent TOKEN_UPDATE broadcast for Unity")
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
        // Preserve saved credentials for quick login, clear only auth data
        val savedUser = prefs.getString(USERNAME, null)
        val savedPass = prefs.getString(USER_PASS, null)
        
        // CRITICAL: We only want to clear tokens that Unity uses, 
        // NOT the main app's session if we want to stay logged in on the Kotlin side.
        // However, usually 'logout' means logging out of the whole app.
        // If the user says "it is asking me to login", it means the Kotlin app's session was cleared.
        
        // Let's only clear the Unity-specific keys in the main prefs, not the whole file.
        // Use apply() instead of commit() to avoid blocking the thread
        prefs.edit()
            .remove(USER_TOKEN)
            .remove("auth_token")
            .remove("access_token")
            .remove("access")
            .remove(REFRESH_TOKEN)
            .remove("refresh")
            .remove("refreshToken")
            .apply()
        
        try {
            // Use reflection to avoid NoClassDefFoundError at runtime
            val clazz = Class.forName("com.unity3d.player.UnityTokenHolder")
            val method = clazz.getMethod("clear")
            method.invoke(null)
            android.util.Log.d("SessionManager", "UnityTokenHolder cleared via reflection")
        } catch (e: Exception) {
            android.util.Log.e("SessionManager", "UnityTokenHolder cleanup skipped or failed: ${e.message}")
        }

        // Clear Unity PlayerPrefs to sync logout
        try {
            val standalonePackageName = "com.company.dicegame"
            val pkg = context.packageName
            
            // List of Unity-specific files to clear COMPLETELY
            val unitySpecificFiles = arrayOf(
                "$standalonePackageName.v2.playerprefs",
                "$pkg.v2.playerprefs",
                "UnityPlayerPrefs",
                "dicegame.v2.playerprefs",
                "PlayerPrefs",
                standalonePackageName,
                "${pkg}.playerprefs"
            )

            for (prefName in unitySpecificFiles) {
                try {
                    // Use apply() instead of commit() to avoid blocking
                    context.getSharedPreferences(prefName, Context.MODE_PRIVATE).edit().clear().apply()
                } catch (e: Exception) {
                    android.util.Log.e("SessionManager", "Failed to clear pref $prefName: ${e.message}")
                }
            }

            // For files shared with the main app, only clear the token keys
            val sharedFiles = arrayOf("gunduata_prefs", "${pkg}_preferences", pkg)
            for (prefName in sharedFiles) {
                try {
                    context.getSharedPreferences(prefName, Context.MODE_PRIVATE).edit().also { e ->
                        e.remove("auth_token")
                        e.remove("access_token")
                        e.remove("access")
                        e.remove("token")
                        e.remove("refresh_token")
                        e.remove("refresh")
                        e.remove("refreshToken")
                        e.remove("user_token")
                        e.putString("is_logged_in", "false")
                        e.putString("logout_requested", "true")
                        e.putLong("logout_timestamp", System.currentTimeMillis())
                        e.apply() // Use apply() instead of commit()
                    }
                } catch (e: Exception) {
                    android.util.Log.e("SessionManager", "Failed to update shared pref $prefName: ${e.message}")
                }
            }

            android.util.Log.d("SessionManager", "Cleared Unity tokens while preserving app session")

            // BROADCAST: Notify running Unity activity to logout immediately
            try {
                com.sikwin.app.utils.UnityTokenHelper.sendLogoutToUnity(context)
            } catch (e: Exception) {
                android.util.Log.e("SessionManager", "sendLogoutToUnity failed: ${e.message}")
            }
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
