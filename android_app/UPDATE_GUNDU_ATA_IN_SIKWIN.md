# How to Update Gundu Ata in Sikwin App

## Why the APK-copy approach caused a freeze

Copying libs and assets from **Gundu Ata 3.apk** into Sikwin's unityLibrary caused the game to freeze because:

1. **libmain.so mismatch** – Gundu Ata 3 is a standalone APK built for its own launcher. Sikwin uses **GameActivity** (UnityPlayerGameActivity). The `libmain.so` from Gundu Ata 3 does not match Sikwin’s GameActivity setup.

2. **Unity version mismatch** – Gundu Ata 3 may use a different Unity version. Mixing libs from different Unity builds leads to crashes or freezes.

3. **Assets vs code** – Unity assets (`data.unity3d`, etc.) must match the compiled code (`libgame.so`, `libil2cpp.so`). They must come from the same Unity build.

## Correct way to update

### Option A: Unity Export (recommended)

1. Open the **Gundu Ata 3** Unity project in Unity Editor.
2. **File → Build Settings** → select **Android**.
3. Choose **Export Project** (not Build APK).
4. Export to a folder (e.g. `unityExport`).
5. Replace Sikwin’s unityLibrary:
   ```bash
   rm -rf android_app/unityLibrary
   cp -R unityExport/unityLibrary android_app/
   # Copy over Sikwin-specific files (UnityTokenHolder, UnityPlayerGameActivity patches)
   ```
6. Build Sikwin:
   ```bash
   cd android_app && ./gradlew assembleRelease -PskipIl2CppBuild
   adb install -r app/build/outputs/apk/release/app-release.apk
   ```

### Option B: Use the export script (if Unity project exists)

```bash
cd android_app
./export_unity_android.sh /tmp/gundu_ata3_export
cp -R /tmp/gundu_ata3_export/unityLibrary unityLibrary
./gradlew assembleRelease -PskipIl2CppBuild
```

## Current state

The Sikwin app has been **restored to the previous working version** (before the Gundu Ata 3 update). The game should run without freezing.

To get Gundu Ata 3 into Sikwin, use a fresh Unity export from the Gundu Ata 3 project as described above.
