# Stream Test Findings – Token Passing Issue

## Summary

**Tokens ARE passing** from Kotlin to Unity. The issue is the **built unityLibrary** lacks methods to switch the UI to gameplay.

## What Works

- ✅ **UnityTokenHolder** – Tokens stored before launch, Unity reads them
- ✅ **Intent extras** – token, auth_token, access, refresh passed correctly
- ✅ **SharedPreferences** – syncAuthToUnity writes to gunduata_prefs, etc.
- ✅ **Broadcast TOKEN_UPDATE** – Received by UnityPlayerGameActivity
- ✅ **GameManager.SetAccessAndRefreshTokens** – Tokens reach GameManager
- ✅ **GameManager.SetToken** – Tokens reach GameManager

## Root Cause (from logcat)

```
MissingMethodException: Method 'UIManager.ShowPanel' not found.
```

- `UnitySendMessage("UIManager", "ShowPanel", "4")` fails because the built binary has `ShowPanel(UIPanelType)` (enum) but **not** `ShowPanel(string)`.
- UnitySendMessage needs an exact method match; the string overload is missing in the built unityLibrary.

## Fix Applied

1. **Removed** the failing `UnitySendMessage("UIManager", "ShowPanel", "4")` call to stop error spam.
2. **Added** `UnitySendMessage("GameManager", "ShowGameplayFromAndroid", "")` – may work if that method exists in the built binary.

## Permanent Fix Required

**Re-export Unity** so the built unityLibrary includes:

- `UIManager.ShowPanel(string panelStr)` – for `UnitySendMessage("UIManager", "ShowPanel", "4")`
- `GameManager.SetAccessAndRefreshTokens` – that calls `UIManager.ShowPanel(Gameplay)` internally
- `GameManager.ShowGameplayFromAndroid` – direct gameplay switch

See **UNITY_REEXPORT_INSTRUCTIONS.md** for steps.

## How to Reproduce

```bash
# Install and launch Unity with tokens
adb shell am start -n com.sikwin.app/com.unity3d.player.UnityPlayerGameActivity \
  -e token "test123" -e auth_token "test123" -e access "test123" \
  -e refresh_token "ref456" -e refresh "ref456" -e username "testuser"

# Check logs
adb logcat -d | grep -E "UnityLoginBypass|Unity|MissingMethod"
```
