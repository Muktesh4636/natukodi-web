# Unity Re-Export Required for Login Fix

The app still shows the Unity login screen after logging in from Kotlin because the **built unityLibrary** was created from an older Unity export and does not include the recent fixes.

## Root Cause

The built `GameManager.SetAccessAndRefreshTokens` only sets tokens via `apiClient.SetAccessAndRefreshTokens` — it **never calls** `UIManager.ShowPanel(UIPanelType.Gameplay)`. So even when tokens are injected correctly, the login screen stays visible.

## What Was Fixed (in C# source)

1. **GameManager** – `SetAccessAndRefreshToken` / `SetAccessAndRefreshTokens` now call `UIManager.Instance.ShowPanel(UIPanelType.Gameplay)` after setting tokens. Also loads token from PlayerPrefs at Start.
2. **UIManager** – Added `ShowPanel(string)` overload to support `UnitySendMessage("UIManager", "ShowPanel", "4")` (4 = Gameplay).
3. **UnityPlayerGameActivity** – Sends `UnitySendMessage("UIManager", "ShowPanel", "4")` as fallback when injecting tokens.

## How to Re-Export Unity

1. **Open Unity Editor** and load the project:
   - `android_app/unity/DiceGame`

2. **File → Build Settings** → select **Android**

3. **Export Project** (or **Build** if you need an APK):
   - Use **Export Project** to generate an Android project with `unityLibrary`
   - Export to a temporary folder (e.g. `unityExport`)

4. **Replace unityLibrary**:
   - Copy the exported `unityLibrary` folder
   - Replace `android_app/unityLibrary` with it

5. **Build and install**:
   ```bash
   cd android_app && ./gradlew installDebug
   ```

## Alternative: Use Unity Hub

1. Open Unity Hub
2. Add the project from `android_app/unity/DiceGame`
3. Open with the Unity version in `ProjectSettings/ProjectVersion.txt`
4. Follow steps 2–5 above

## Command-Line Export (Batch Mode)

You can export without opening the Unity Editor:

```bash
cd android_app
./export_unity_android.sh
```

This runs Unity in batch mode and exports to `android_app/unityExport`. Then:

```bash
cp -R unityExport/unityLibrary unityLibrary
./gradlew assembleRelease -PskipIl2CppBuild
adb install -r app/build/outputs/apk/release/app-release.apk
```

**Requirements:**
- Unity 6000.3.8f1 installed via Unity Hub (default path: `/Applications/Unity/Hub/Editor/6000.3.8f1/`)
- Or set `UNITY_PATH` to your Unity executable

**Custom output path:**
```bash
./export_unity_android.sh /tmp/my_export
```
