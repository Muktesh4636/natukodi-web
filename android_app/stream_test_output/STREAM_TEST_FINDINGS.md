# Stream Test Findings - Gundu Ata Freeze

## Summary
The game **launches successfully** (UnityPlayerGameActivity opens in ~829ms) but appears frozen due to **Unity API mismatches** between Sikwin's Android code and Gundu Ata 3's Unity build.

## Root Causes

### 1. GameApiClient.SetAccessAndRefreshToken - Wrong Parameters
```
E/Unity: Failed to call function SetAccessAndRefreshToken of class GameApiClient
E/Unity: Calling function SetAccessAndRefreshToken with 1 parameter but the function requires 2.
```
- **Sikwin sends**: 1 param (JSON string)
- **Gundu Ata 3 expects**: 2 params (accessToken, refreshToken)
- **Fix**: Only call `GameManager.SetAccessAndRefreshToken(json)` - GameManager accepts 1 JSON param and internally calls GameApiClient correctly. Remove direct calls to GameApiClient.

### 2. UIManager.ShowPanel - Method Not Found
```
E/Unity: MissingMethodException: Method 'UIManager.ShowPanel' not found.
```
- **Sikwin sends**: `UnitySendMessage("UIManager", "ShowPanel", "4")`
- **Gundu Ata 3**: UIManager.ShowPanel exists but takes `int panel` - may not be ready at call time or signature differs
- **Fix**: Remove or delay UIManager.ShowPanel calls; let GameManager.ShowGameplayFromAndroid handle UI

## What Works
- App launches, Unity activity opens
- Timer preloading (API calls to gunduata.online)
- Token broadcast and UnityTokenHolder
- Surface/layout (1440x3120)

## Script
Run: `./scripts/stream_test.sh` to reproduce and capture logs.
