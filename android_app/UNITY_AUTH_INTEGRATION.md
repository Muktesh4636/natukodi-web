# Unity Authentication Token Integration Guide

## Overview
This document explains how authentication tokens are synchronized between the Kotlin Android app and the Unity game, enabling seamless single sign-on (SSO) functionality.

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────┐
│   Kotlin App    │─────────▶│ SharedPreferences │─────────▶│ Unity Game  │
│  (Login Screen) │  Store   │  "gunduata_prefs" │  Read    │  (Auto-login)│
└─────────────────┘         └──────────────────┘         └─────────────┘
```

## Flow Diagram

```
1. User Logs In (Kotlin App)
   ↓
2. Token Saved to SharedPreferences
   ├── "user_token" (for Kotlin app)
   └── "auth_token" (for Unity)
   ↓
3. User Clicks "Gundu Ata"
   ↓
4. Unity Activity Launched
   ├── Intent extras passed
   └── SharedPreferences already populated
   ↓
5. Unity Reads Authentication
   ├── Primary: SharedPreferences "gunduata_prefs"
   └── Fallback: Intent extras
   ↓
6. Unity Auto-Login
   └── User authenticated automatically
```

## Implementation Details

### 1. Token Storage (SessionManager.kt)

**Location**: `android_app/app/src/main/java/com/sikwin/app/data/auth/SessionManager.kt`

#### Key Function: `saveAuthToken()`

```kotlin
fun saveAuthToken(token: String) {
    // Store in both formats for compatibility
    // Unity expects "auth_token" but we also keep "user_token" for our app
    prefs.edit()
        .putString(USER_TOKEN, token)      // "user_token" - for Kotlin app
        .putString("auth_token", token)     // "auth_token" - for Unity
        .apply()
}
```

**Why both keys?**
- `"user_token"`: Used by the Kotlin app internally
- `"auth_token"`: Expected by Unity's `UnityPlayerGameActivity.java`

#### Key Function: `fetchAuthToken()`

```kotlin
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
```

**Migration Logic**: Automatically migrates existing sessions that only have `"user_token"` to also include `"auth_token"`.

### 2. Login Process (GunduAtaViewModel.kt)

**Location**: `android_app/app/src/main/java/com/sikwin/app/ui/viewmodels/GunduAtaViewModel.kt`

```kotlin
fun login(username: String, password: String) {
    viewModelScope.launch {
        // ... API call ...
        if (response.isSuccessful) {
            val authResponse = response.body()
            authResponse?.let {
                sessionManager.saveAuthToken(it.access)      // Stores as both keys
                sessionManager.saveRefreshToken(it.refresh)
                sessionManager.saveUsername(it.user.username)
                sessionManager.saveUserId(it.user.id)
                sessionManager.savePassword(password)
                
                // Sync to Unity PlayerPrefs for seamless login
                sessionManager.syncAuthToUnity()  // ← Additional sync step
            }
        }
    }
}
```

### 3. Unity Launch (AppNavigation.kt)

**Location**: `android_app/app/src/main/java/com/sikwin/app/navigation/AppNavigation.kt`

#### Key Function: `launchGame()`

```kotlin
fun launchGame() {
    // 1. Verify user is logged in
    if (!viewModel.loginSuccess) {
        showAuthDialog = true
        return
    }

    // 2. Get authentication data
    val authToken = sessionManager.fetchAuthToken()
    val refreshToken = sessionManager.fetchRefreshToken()
    val username = sessionManager.fetchUsername()
    val userId = sessionManager.fetchUserId()
    val password = sessionManager.fetchPassword()

    // 3. Verify token exists
    if (authToken == null || authToken.isEmpty()) {
        Toast.makeText(context, "Authentication error. Please login again.", Toast.LENGTH_LONG).show()
        return
    }

    // 4. Sync to Unity PlayerPrefs BEFORE launching
    sessionManager.syncAuthToUnity()

    // 5. Create Intent with authentication data
    val intent = Intent(context, UnityPlayerGameActivity::class.java)
    
    // Pass via Intent extras (fallback method)
    intent.putExtra("token", authToken)              // Primary key Unity looks for
    intent.putExtra("auth_token", authToken)
    intent.putExtra("refresh_token", refreshToken)
    intent.putExtra("username", username)
    intent.putExtra("user_id", userId)
    intent.putExtra("password", password)

    // 6. Launch Unity
    context.startActivity(intent)
}
```

### 4. Unity Reading Authentication (UnityPlayerGameActivity.java)

**Location**: `android_app/unityLibrary/src/main/java/com/unity3d/player/UnityPlayerGameActivity.java`

#### Key Function: `sendLoginDataToUnity()`

```java
private void sendLoginDataToUnity() {
    // STEP 1: Read from SharedPreferences (PRIMARY METHOD)
    SharedPreferences appPrefs = getSharedPreferences("gunduata_prefs", MODE_PRIVATE);
    
    String _token = appPrefs.getString("auth_token", null);        // ← Reads this key!
    String _refreshToken = appPrefs.getString("refresh_token", null);
    String _username = appPrefs.getString("username", null);
    String _password = appPrefs.getString("user_pass", null);
    String _userId = ... // Reads user_id (stored as Int)

    // STEP 2: Fallback to Intent extras if SharedPreferences empty
    Intent intent = getIntent();
    if (_token == null && intent != null) {
        _token = intent.getStringExtra("token");              // ← Fallback key
        _refreshToken = intent.getStringExtra("refresh_token");
        _username = intent.getStringExtra("username");
        _userId = intent.getStringExtra("user_id");
        _password = intent.getStringExtra("password");
    }

    // STEP 3: Auto-login if token found
    if (token != null && !token.isEmpty()) {
        // Save to Unity PlayerPrefs
        saveToPlayerPrefs(username, password, token);
        
        // Send JSON to Unity game via UnitySendMessage
        JSONObject json = new JSONObject();
        json.put("access", token);
        json.put("token", token);
        json.put("username", username);
        json.put("user_id", userId);
        // ... more fields
        
        // Inject into Unity game (multiple attempts for reliability)
        UnityPlayer.UnitySendMessage("GameApiClient", "OnAndroidLogin", jsonString);
    }
}
```

## SharedPreferences Structure

### Android App Preferences (`"gunduata_prefs"`)
```
Key              | Value Type | Purpose
-----------------|------------|------------------
user_token       | String     | Token for Kotlin app
auth_token       | String     | Token for Unity (PRIMARY)
refresh_token    | String     | Refresh token
username         | String     | User's username
user_id          | Int        | User's ID
user_pass        | String     | User's password (for Unity)
```

### Unity PlayerPrefs (`"{packageName}.v2.playerprefs"`)
```
Key              | Value Type | Purpose
-----------------|------------|------------------
auth_token       | String     | Authentication token
user_token       | String     | Alternative token key
bearer_token     | String     | Bearer token format
username         | String     | Username
user_id          | String     | User ID
is_logged_in     | String     | "true" or "false"
auto_login       | String     | "true" flag
from_android_app | String     | "true" flag
```

## Logout Flow

### Kotlin App Logout

**Location**: `SessionManager.kt` → `logout()`

```kotlin
fun logout() {
    // 1. Clear Android app preferences
    prefs.edit().clear().apply()
    
    // 2. Clear Unity PlayerPrefs and set logout flags
    val unityPrefs = context.getSharedPreferences(unityPrefsName, Context.MODE_PRIVATE)
    unityPrefs.edit()
        .clear()
        .putString("is_logged_in", "false")
        .putString("logout_requested", "true")
        .putLong("logout_timestamp", System.currentTimeMillis())
        .apply()
}
```

**Location**: `GunduAtaViewModel.kt` → `logout()`

```kotlin
fun logout(context: android.content.Context? = null) {
    // Clear Unity authentication before clearing session
    if (context != null) {
        clearUnityAuthentication(context)
    }
    
    // Clear session (also clears Unity PlayerPrefs)
    sessionManager.logout()
    
    // Clear ViewModel state
    userProfile = null
    wallet = null
    loginSuccess = false
    // ... clear other state
}
```

## Key Points

### 1. Dual Storage Strategy
- **Primary**: SharedPreferences `"gunduata_prefs"` with key `"auth_token"`
- **Fallback**: Intent extras with key `"token"`
- **Why**: Ensures Unity can read authentication even if one method fails

### 2. Key Naming Convention
- Unity expects `"auth_token"` in SharedPreferences
- Unity expects `"token"` in Intent extras
- Kotlin app uses `"user_token"` internally
- **Solution**: Store token with both keys for compatibility

### 3. Migration Support
- Automatically migrates existing sessions
- Copies `"user_token"` → `"auth_token"` if missing
- Ensures backward compatibility

### 4. Timing
- Token synced **before** Unity launch
- Unity reads **immediately** on activity start
- Multiple injection attempts ensure reliability

## Debugging

### Check if Token is Stored

```bash
# Via ADB
adb shell run-as com.sikwin.app cat /data/data/com.sikwin.app/shared_prefs/gunduata_prefs.xml
```

### Check Logcat Messages

Look for these log tags:
- `SessionManager`: Token storage/migration
- `AppNavigation`: Unity launch and token passing
- `UnityLoginBypass`: Unity authentication injection

### Common Issues

1. **Unity still asks for login**
   - Check if `"auth_token"` exists in SharedPreferences
   - Verify Unity is reading from correct SharedPreferences name
   - Check logcat for Unity authentication logs

2. **Token not found**
   - Ensure user logged in successfully
   - Check `saveAuthToken()` is called after login
   - Verify migration logic ran (check logs)

3. **Logout not syncing**
   - Verify `logout()` clears both SharedPreferences
   - Check Unity reads `"logout_requested"` flag
   - Ensure Unity checks logout flags on startup

## Files Modified

1. **SessionManager.kt**
   - `saveAuthToken()`: Stores token with both keys
   - `fetchAuthToken()`: Reads both keys + migration
   - `syncAuthToUnity()`: Syncs to Unity PlayerPrefs
   - `logout()`: Clears both app and Unity prefs

2. **GunduAtaViewModel.kt**
   - `login()`: Calls `syncAuthToUnity()` after login
   - `logout()`: Accepts context and clears Unity auth

3. **AppNavigation.kt**
   - `launchGame()`: Verifies token, syncs, and passes via Intent

4. **ProfileScreen.kt**
   - Logout button: Passes context to `viewModel.logout()`

## Testing Checklist

- [ ] User logs in → Token stored with both keys
- [ ] User clicks "Gundu Ata" → Unity launches
- [ ] Unity reads token from SharedPreferences
- [ ] Unity auto-authenticates without login prompt
- [ ] User logs out → Both apps logged out
- [ ] Existing sessions migrate correctly
- [ ] Intent extras work as fallback

## Future Improvements

1. **Token Refresh**: Automatically refresh expired tokens
2. **Security**: Encrypt tokens in SharedPreferences
3. **Biometric Auth**: Add fingerprint/face unlock
4. **Session Timeout**: Auto-logout after inactivity
5. **Multi-Device**: Sync sessions across devices

## References

- Unity Android Integration: [Unity Documentation](https://docs.unity3d.com/Manual/android.html)
- Android SharedPreferences: [Android Documentation](https://developer.android.com/reference/android/content/SharedPreferences)
- Intent Extras: [Android Documentation](https://developer.android.com/reference/android/content/Intent)

---

**Last Updated**: February 2025  
**Version**: 1.0  
**Author**: Development Team
