# Sikwin APK Crash Analysis Report
**Date:** February 19, 2026  
**Device:** R5CX61T3EVW (Samsung)  
**App:** com.sikwin.app  
**Issue:** Unity Game (Gundu Ata) crashes immediately on launch

---

## Executive Summary
The Sikwin app launches successfully and displays the home screen correctly. However, when navigating to the Gundu Ata game (Unity activity), the app **crashes with a JNI FatalError** and returns to the launcher.

---

## Crash Details

### Crash Type
- **Signal:** SIGABRT (Signal 6)
- **Error:** `JNI FatalError called: com/unity3d/player/UnityPlayerForActivityOrService`
- **Location:** `UnityPlayerGameActivity.onCreate()` at line 58

### Root Cause
The Unity native library (`libgame.so`) is attempting to find the Java class `com.unity3d.player.UnityPlayerForActivityOrService` via JNI's `FindClass()` method, but **the class cannot be found at runtime**, causing a JNI FatalError and immediate crash.

### Stack Trace
```
F/ikwin.app:unity(18194): jni_internal.cc:828] JNI FatalError called: com/unity3d/player/UnityPlayerForActivityOrService
F/libc(18194): Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid 18194 (ikwin.app:unity)
F/DEBUG(18217): Abort message: 'JNI FatalError called: com/unity3d/player/UnityPlayerForActivityOrService'

at com.unity3d.player.UnityPlayerGameActivity.onCreate(UnityPlayerGameActivity.java:58)
at android.app.Activity.performCreate(Activity.java:9363)
```

---

## Technical Analysis

### What's Happening
1. User taps "Gundu Ata" navigation button in the Sikwin app
2. Android starts `com.unity3d.player.UnityPlayerGameActivity`
3. In `onCreate()`, the code attempts to preload Unity classes:
   ```java
   Class.forName("com.unity3d.player.UnityPlayerForActivityOrService");
   Class.forName("com.unity3d.player.UnityPlayerForGameActivity");
   ```
4. The `Class.forName()` calls succeed (Java classes exist)
5. Then `UnityInitializeFromUIThead(this)` is called (line 63)
6. This native method loads `libgame.so` which internally tries to find Unity classes via JNI
7. **JNI FindClass fails** to locate `UnityPlayerForActivityOrService`
8. Unity native code calls `JNI FatalError()` which triggers SIGABRT
9. App crashes and user is returned to launcher

### Why JNI FindClass Fails

The issue is **ClassLoader context**. When Unity's native code calls `FindClass("com/unity3d/player/UnityPlayerForActivityOrService")`, it uses the **system ClassLoader** which doesn't have access to the app's classes. This is a common issue with Unity integration.

### Files Involved
- **Crash location:** `android_app/unityLibrary/src/main/java/com/unity3d/player/UnityPlayerGameActivity.java:58`
- **Missing at runtime:** `com.unity3d.player.UnityPlayerForActivityOrService`
- **Native library:** `libgame.so` (Unity runtime)

---

## Evidence

### Logcat Excerpts

**App Launch (Successful):**
```
02-19 14:44:52.302 D/SessionManager(17458): Syncing auth data to Unity PlayerPrefs
02-19 14:44:52.316 D/SGM:FgCheckThread(2557): getForegroundApp(), foregroundPkgName=com.sikwin.app
```

**Navigation to Unity Activity:**
```
02-19 14:44:50.036 D/ActivityTaskManager(2557): startActivityAsUser: com.sikwin.app/com.unity3d.player.UnityPlayerGameActivity
02-19 14:44:50.048 I/ActivityTaskManager(2557): START u0 {cmp=com.sikwin.app/com.unity3d.player.UnityPlayerGameActivity}
```

**Crash:**
```
02-19 14:44:50.428 F ikwin.app:unity: JNI FatalError called: com/unity3d/player/UnityPlayerForActivityOrService
02-19 14:44:50.503 F libc: Fatal signal 6 (SIGABRT)
02-19 14:44:50.643 F DEBUG: Abort message: 'JNI FatalError called: com/unity3d/player/UnityPlayerForActivityOrService'
```

**App Exit:**
```
02-19 14:45:31.715 I/WindowManager(2557): Application Error: com.sikwin.app
02-19 14:45:32.148 W/ActivityTaskManager(2557): Activity top resumed state loss timeout
02-19 14:45:32.567 D/SGM:FgCheckThread(2557): pkgName: com.sikwin.app is not in foreground
```

### UI Hierarchy Before Crash
The app was displaying the home screen correctly with:
- User balance: ₹249,516.00
- Navigation buttons: Home, Gundu Ata, Me
- Search bar and game cards visible
- All UI elements rendering properly

---

## Reproduction Steps
1. Launch Sikwin app (`com.sikwin.app`)
2. Wait for home screen to load (successful)
3. Tap "Gundu Ata" button in bottom navigation
4. **Crash occurs immediately** - app exits to launcher
5. "Application Error" dialog may briefly appear

**Reproducibility:** 100% - crashes every time

---

## Solutions

### Solution 1: Fix JNI ClassLoader Context (Recommended)
The Unity native code needs to use the correct ClassLoader when calling `FindClass()`. This requires modifying the native Unity integration.

**Implementation:**
1. Pass the Java ClassLoader to native code before calling `FindClass()`
2. Use `JNIEnv->FindClass()` with the app's ClassLoader instead of system ClassLoader
3. Cache the class references in native code after successful lookup

**File to modify:** Unity native integration (requires Unity project source)

### Solution 2: Preload Classes Before Native Init
Move the `Class.forName()` calls to happen **before** loading the native library.

**Current code (UnityPlayerGameActivity.java:52-64):**
```java
@Override
protected void onCreate(Bundle savedInstanceState) {
    try {
        Class.forName("com.unity3d.player.UnityPlayerForActivityOrService");
        Class.forName("com.unity3d.player.UnityPlayerForGameActivity");
    } catch (Throwable t) {
        Log.e("UnityPlayerPatch", "Failed to preload Unity glue classes", t);
    }
    UnityInitializeFromUIThead(this);  // <-- Native init happens here
    super.onCreate(savedInstanceState);
}
```

**Problem:** Classes are preloaded, but native code still can't find them via JNI.

### Solution 3: Use Static Initializer (Try This First)
Move class preloading to a static initializer block that runs before any native code.

**Add to UnityPlayerGameActivity.java:**
```java
static {
    // Preload Unity classes BEFORE native library loads
    try {
        Class.forName("com.unity3d.player.UnityPlayerForActivityOrService");
        Class.forName("com.unity3d.player.UnityPlayerForGameActivity");
        Class.forName("com.unity3d.player.UnityPlayer");
    } catch (Throwable t) {
        android.util.Log.e("UnityPlayerPatch", "Failed to preload Unity classes", t);
    }
    System.loadLibrary("game");
}
```

### Solution 4: Check ProGuard/R8 Rules
Ensure Unity classes are not being obfuscated or removed by ProGuard/R8.

**Add to proguard-rules.pro:**
```
-keep class com.unity3d.player.** { *; }
-keepclassmembers class com.unity3d.player.** { *; }
```

### Solution 5: Verify Unity Library Export
Check that `UnityPlayerForActivityOrService` is properly included in the Unity library export.

---

## Immediate Next Steps

1. **Check ProGuard rules** - Verify Unity classes aren't being stripped
2. **Try Solution 3** - Move class loading to static initializer
3. **Check Unity export settings** - Ensure all required classes are exported
4. **Test with debug build** - See if issue persists without obfuscation
5. **Check Unity version compatibility** - Verify Unity version matches Android Gradle plugin

---

## Additional Information

### Device Info
- **Model:** Samsung (R5CX61T3EVW)
- **Android Version:** Unknown (API level supports GameActivity)
- **ADB Connected:** Yes

### App State
- **Package:** com.sikwin.app
- **Process ID:** 17458 (main), 18194 (unity - crashed)
- **User:** u0_a685 (UID 10685)
- **Installation:** Successful
- **Main Activity:** Works perfectly
- **Unity Activity:** Crashes on launch

### Files to Review
1. `android_app/unityLibrary/src/main/java/com/unity3d/player/UnityPlayerGameActivity.java`
2. `android_app/unityLibrary/src/main/java/com/unity3d/player/UnityPlayerForActivityOrService.java`
3. `android_app/unityLibrary/src/main/java/com/unity3d/player/UnityPlayerForGameActivity.java`
4. `android_app/app/proguard-rules.pro`
5. `android_app/unityLibrary/proguard-rules.pro`

---

## Conclusion

The Sikwin app's main functionality works correctly, but the Unity game integration has a **critical JNI ClassLoader issue** preventing the game from launching. The crash is consistent and reproducible. The solution requires either:
1. Fixing the native Unity integration to use the correct ClassLoader
2. Adjusting the class loading sequence to ensure JNI can find the required classes
3. Verifying ProGuard/R8 isn't stripping the Unity classes

**Priority:** CRITICAL - Game is completely non-functional
**Impact:** Users cannot play Gundu Ata game
**Workaround:** None - requires code fix and rebuild

---

*Report generated from live device testing via ADB*
