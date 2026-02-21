# APK Release Checklist

When you release a new APK update, follow these steps so users see the update prompt correctly.

## 1. Bump version in Android app

Edit `android_app/app/build.gradle`:

```gradle
defaultConfig {
    versionCode 2      // Increment: 1 → 2 → 3 ...
    versionName "1.1"  // Display version (e.g. 1.0, 1.1, 2.0)
}
```

## 2. Build and upload the new APK

- Build the release APK
- Upload it to your server (e.g. `https://gunduata.online/gundu-ata.apk`)
- Ensure the download URL is accessible

## 3. Update Game Settings in Admin Panel

1. Go to **Game Admin** → **Game Settings** (`/game-admin/game-settings/`)
2. Scroll to **📱 App Version (APK Update Prompt)**
3. Update:
   - **Version Code**: Must match `versionCode` from build.gradle (e.g. `2`)
   - **Version Name**: Display name shown to users (e.g. `1.1`)
   - **APK Download URL**: Full URL to the new APK (e.g. `https://gunduata.online/gundu-ata.apk`)
   - **Force Update**: Enable only if users must update to continue (blocks app until updated)
4. Click **Save All Settings**

## 4. Verify

- Users with older versions will see "New Update Available" when they open the app
- Tapping "Update" opens the download URL
- If Force Update is enabled, users cannot dismiss the dialog

## First-time setup

If app version settings don't exist yet, run:

```bash
cd backend
python manage.py init_game_settings
```

Or visit Game Settings and save – the form will create the defaults.
