# Gundu Ata Button Click - Crash Analysis Report

**Date:** February 19, 2026, 14:53:51
**Test Device:** R5CX61T3EVW
**App Package:** com.sikwin.app

---

## Test Summary

✅ **Step 1:** Found Gundu Ata button coordinates
✅ **Step 2:** Successfully clicked the button
❌ **Step 3:** App crashed during Unity game initialization

---

## 1. Gundu Ata Button Coordinates

The Gundu Ata button was found in the bottom navigation bar:

- **Bounds:** [490, 2764] to [950, 3064]
- **Center Point:** (720, 2914)
- **Location:** Bottom navigation bar (middle tab)
- **Element Type:** Clickable View with TextView

---

## 2. Click Action

The button was successfully clicked at coordinates (720, 2914) using:
```bash
adb shell input tap 720 2914
```

The system successfully started the `UnityPlayerGameActivity`:
```
START u0 {flg=0x34000000 cmp=com.sikwin.app/com.unity3d.player.UnityPlayerGameActivity (has extras)}
```

---

## 3. Crash Analysis

### Crash Type: **Native Crash**

**Process ID:** 29407
**Crash Time:** 02-19 14:53:51.406

### Root Cause

```
java.lang.NoSuchMethodError: no static or non-static method 
"Lcom/unity3d/player/UnityPlayerForActivityOrService;.nativeSoftInputClosed()V"
```

### Detailed Error

```
Failed to register native method 
com.unity3d.player.UnityPlayerForActivityOrService.nativeSoftInputClosed()V 
in /data/app/.../base.apk!classes2.dex
```

### Stack Trace

```
at com.unity3d.player.UnityPlayer.<clinit>(UnityPlayer.java:75)
at com.unity3d.player.UnityPlayerGameActivity.<clinit>(UnityPlayerGameActivity.java:50)
```

### What Happened

1. User clicked the "Gundu Ata" button in the bottom navigation
2. Android started `UnityPlayerGameActivity`
3. During class initialization (`<clinit>`), Unity attempted to register native methods
4. The native method `nativeSoftInputClosed()` was not found in the Unity native library
5. This caused a `NoSuchMethodError` during static initialization
6. The app crashed before the Unity game could load

---

## 4. Technical Details

### Missing Native Methods

The Unity native library (`libunity.so`) failed to provide the following method:
- `com.unity3d.player.UnityPlayerForActivityOrService.nativeSoftInputClosed()V`

This method is part of Unity's soft keyboard input handling system.

### Impact

- The game **never loaded** - crash occurred during initialization
- The crash happens in the **static initializer** of `UnityPlayer` class
- This is a **critical failure** that prevents any Unity content from running

---

## 5. System Response

```
ActivityManager: crash : com.sikwin.app,10685
ActivityManager: Showing crash dialog for package com.sikwin.app u0
DropBoxManagerService: add tag=data_app_native_crash
```

Android detected the native crash and showed a crash dialog to the user.

---

## 6. Conclusion

**Result:** ❌ **CRASHED**

The Gundu Ata game **failed to launch** due to a missing native method in the Unity player library. The crash occurs immediately during Unity initialization, before any game content can be loaded.

### Recommended Actions

1. **Verify Unity Player Files:** Check if all Unity native libraries are properly included
2. **Unity Version Mismatch:** The Java classes may be from a different Unity version than the native library
3. **Check Build Configuration:** Ensure Unity export settings match the Android project configuration
4. **Review Custom Unity Player:** If using custom Unity player classes, ensure all native methods are implemented

---

## Log Files

Full logcat saved to: `/tmp/gundu_ata_logcat.txt`
- Total relevant log lines: 367
- Crash dump performed by: crash_dump64 (pid 29431)
- Tombstone created by: tombstoned (pid 1256)
