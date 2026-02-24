# Unity Re-Export Instructions (Required for Auto-Login)

## Why You're Still Seeing the Login Screen

The **built `unityLibrary`** in `android_app/unityLibrary/` was produced from an older Unity export. It does **not** include the auto-login logic:

| Component | Built (current) | Source (needed) |
|-----------|-----------------|-----------------|
| **GameManager.Start()** | Only subscribes OnLoginSuccess | Checks PlayerPrefs for `auth_token`, shows gameplay if present |
| **GameManager.SetAccessAndRefreshTokens()** | Only stores token in ApiClient | Also calls InitWebSocket, FetchInitialData, **UIManager.ShowPanel(Gameplay)** |
| **UIManager.ShowPanel(string)** | Does not exist | Exists for `UnitySendMessage("UIManager", "ShowPanel", "4")` |
| **UIManager.AutoLoginIfPossible()** | Checks username+password only | Checks `auth_token` first, shows gameplay if present |

Your Kotlin `sendTokensToUnity` and `UnityPlayerGameActivity.sendLoginDataToUnity` correctly send tokens to Unity. The problem is the **built** GameManager receives them but never switches the UI to gameplay.

## Steps to Re-Export

1. **Open Unity Editor** and load the project:
   ```
   android_app/gradle_project/DiceGame-1.0 3/DiceGame/DiceGame-1.0 2/DiceGame/
   ```
   Or:
   ```
   android_app/apk/DiceGame-1.0 2/DiceGame/
   ```

2. **File → Build Settings → Android**

3. **Export Project** (not Build APK):
   - Check "Export Project"
   - Click "Export Project"
   - Choose a temp folder (e.g. `~/unity_export`)

4. **Replace unityLibrary**:
   ```bash
   # From the export folder, copy the unityLibrary
   cp -r ~/unity_export/unityLibrary /Users/pradyumna/gundu_at/android_app/
   ```

5. **Restore our custom UnityPlayerGameActivity** (it gets overwritten):
   - The export may overwrite `unityLibrary/src/main/java/com/unity3d/player/UnityPlayerGameActivity.java`
   - Re-apply our token injection and `sendLoginDataToUnity` logic from git history if needed

6. **Build the app**:
   ```bash
   cd android_app && ./gradlew installDebug
   ```

## What the Updated Unity Source Does

- **GameManager.Start()**: On startup, checks `PlayerPrefs` for `auth_token` or `access_token`. If found, loads token, calls InitWebSocket, FetchInitialData, and shows gameplay panel.
- **GameManager.SetAccessAndRefreshTokens(json)**: When tokens arrive via `UnitySendMessage`, parses JSON, sets tokens in ApiClient, InitWebSocket, FetchInitialData, and **UIManager.ShowPanel(Gameplay)**.
- **UIManager.ShowPanel(string)**: Accepts "4" for Gameplay panel, so `UnitySendMessage("UIManager", "ShowPanel", "4")` works.

## Temporary Workaround (Until Re-Export)

If you login with **username + password** (not OTP) and check **"Save password"**, the built binary's `AutoLoginIfPossible` will find username/password in PlayerPrefs and call `LoginUser`, which shows gameplay. This does **not** work for OTP login (no password saved).

## If Export Fails

- **"Build cannot be appended"**: Use a fresh export, don't append to existing.
- **Code coverage / package errors**: Disable code coverage in Unity, ensure all packages resolve.
- **Alternative**: Build APK from Unity, then extract the `unityLibrary` from the generated Gradle project (Unity creates a `launcher` + `unityLibrary` structure).
