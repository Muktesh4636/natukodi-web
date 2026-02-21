# APK Crash Analysis – Why the App Crashes Sometimes

Based on crash logs, existing reports, and codebase analysis.

---

## Summary of Crash Types

| Crash Type | When | Root Cause |
|------------|------|------------|
| **1. JNI FatalError on launch** | Tapping "Gundu Ata" | Unity native code can't find `UnityPlayerForActivityOrService` via JNI FindClass |
| **2. NoSuchMethodError** | Tapping "Gundu Ata" | `nativeSoftInputClosed()` not found in Unity native library |
| **3. SIGABRT during JNI_OnLoad** | Unity init / load | JNI registration fails in `libunity.so` during `System.loadLibrary` |
| **4. After screen rotation** | Device rotation | Unity/GameActivity lifecycle issues during config change |

---

## 1. JNI ClassLoader / FindClass Failure

**Error:** `JNI FatalError called: com/unity3d/player/UnityPlayerForActivityOrService`

**What happens:**
- User taps "Gundu Ata" → `UnityPlayerGameActivity` starts
- `System.loadLibrary("game")` runs in static block (line 85)
- Unity native code (`libunity.so`) calls `FindClass("com/unity3d/player/UnityPlayerForActivityOrService")`
- JNI uses the system ClassLoader, which doesn’t see app classes
- `FindClass` fails → JNI FatalError → SIGABRT

**Why it’s intermittent:** Depends on ClassLoader context and device/Android version.

---

## 2. Missing Native Method (nativeSoftInputClosed)

**Error:** `NoSuchMethodError: no static or non-static method "Lcom/unity3d/player/UnityPlayerForActivityOrService;.nativeSoftInputClosed()V"`

**What happens:**
- During `UnityPlayer` static init, JNI tries to register native methods
- `UnityPlayerForActivityOrService.nativeSoftInputClosed()` is declared in Java
- The corresponding native implementation is missing in `libunity.so`
- Likely Unity version mismatch between Java glue and native libs

---

## 3. SIGABRT in JNI_OnLoad (libunity.so)

**Stack trace (from `unity_crash_next.txt`):**
```
native: #09 pc 0070b660  libunity.so (???)
native: #10 pc 0070b534  libunity.so (JNI_OnLoad+88)
native: #21 com.unity3d.player.UnityPlayer.<clinit>
```

**What happens:**
- `UnityPlayer` class is first used
- Its static init triggers `System.loadLibrary` (via `game` → `unity`)
- Inside `JNI_OnLoad`, Unity registers JNI methods
- Some check fails (e.g. FindClass, method registration) → `FatalError` → SIGABRT

---

## 4. Crashes After Screen Rotation

**File:** `unity_crash_after_autorotation.txt`

**What happens:**
- User rotates device while in Unity game
- `onConfigurationChanged` runs
- Unity/GameActivity may not fully handle config change
- Possible null refs or lifecycle issues during resize/recreate

---

## Current Configuration

- **Unity activity process:** `android:process="${applicationId}"` → main process
- **ProGuard:** `-keep class com.unity3d.player.* { *; }` → Unity classes kept
- **Library load:** `System.loadLibrary("game")` in `UnityPlayerGameActivity` static block
- **GameActivity:** Uses `com.google.androidgamesdk.GameActivity` (newer Unity integration)

---

## Recommended Fixes

### Fix 1: Ensure Unity Version Consistency
- Re-export Unity project and ensure Java glue classes match the native libs
- Use the same Unity version for export and Android build

### Fix 2: Preload Classes Before Native Init
Add to `UnityPlayerGameActivity.java` static block, before `System.loadLibrary`:
```java
static {
    try {
        Class.forName("com.unity3d.player.UnityPlayerForActivityOrService");
        Class.forName("com.unity3d.player.UnityPlayerForGameActivity");
        Class.forName("com.unity3d.player.UnityPlayer");
    } catch (Throwable t) {
        android.util.Log.e("UnityPlayerPatch", "Preload failed", t);
    }
    System.loadLibrary("game");
}
```

### Fix 3: Lock Orientation (Short-term)
To reduce rotation-related crashes, lock orientation:
```xml
android:screenOrientation="portrait"
android:configChanges="..."  <!-- remove "orientation" if you lock it -->
```

### Fix 4: Null Checks in Lifecycle
In `UnityPlayerGameActivity`, guard lifecycle calls:
```java
@Override
public void onConfigurationChanged(Configuration newConfig) {
    if (mUnityPlayer != null) {
        mUnityPlayer.configurationChanged(newConfig);
    }
    super.onConfigurationChanged(newConfig);
}
```

### Fix 5: Try Main Process for Unity
If Unity is in a separate process (`:unity`), ClassLoader issues are more likely. The app manifest uses `android:process="${applicationId}"`, so Unity runs in the main process. Confirm the merged manifest does not override this with `:unity`.

### Fix 6: Debug Build Without Minify
Build a debug APK with `minifyEnabled false` and `shrinkResources false` to rule out ProGuard/R8 stripping.

---

## Files to Inspect

| File | Purpose |
|------|---------|
| `android_app/unityLibrary/src/main/java/com/unity3d/player/UnityPlayerGameActivity.java` | Activity, static block, lifecycle |
| `android_app/app/src/main/AndroidManifest.xml` | Process, configChanges, orientation |
| `android_app/unityLibrary/proguard-unity.txt` | ProGuard rules for Unity |
| Unity export (DiceGame project) | Unity version, export settings, native libs |

---

## Quick Checks

1. **Unity version:** Match export and Android project.
2. **Process:** Ensure Unity activity is in main process, not `:unity`.
3. **ProGuard:** Keep `-keep class com.unity3d.player.*`.
4. **Rotation:** Test with orientation locked vs `fullUser`.
5. **Devices:** Test on multiple devices/Android versions.
