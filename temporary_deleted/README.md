# Temporary deleted – recover anytime

These files were moved here so they are no longer in the main project or in git. **Nothing is permanently deleted** – you can copy or move any file back whenever you need it.

## What’s inside

- **Root unused copies**: `accounts_views_*.py`, `admin_views_server1.py`, `authentication.py`, `fix_*.py`, all `game_engine_v2*.py` (the app uses `backend/game_engine_v2.py` only).
- **Video**: `video/` (e.g. screen recordings).
- **Logs & reports**: `big_logs.txt`, `full_logs_debug.txt`, `unity_*.txt`, `locust_report*.html`, `bet_load_test_report.html`.
- **Screenshots / uploads**: `deposit_screenshots_s1/`, `deposit_screenshots_s3/`, `qr_codes_s3/`, `screenshot_*.jpg`.
- **Docs**: `Message_Central_SDK_Verify_Now_Doc.pdf`.
- **Android APK & Unity**: `backend_apks/` (built APKs from `backend/staticfiles/apks` and `assets`), `unityLibrary/` (Unity export at repo root). If you moved `android_app/` (full Android + Unity project), it will be here as `android_app/`.

## To restore a file

Copy or move it back to the repo root (or the path it was in). Examples:

```bash
cp temporary_deleted/accounts_views_fixed.py ./
mv temporary_deleted/video ./
# Restore Unity library to repo root:
mv temporary_deleted/unityLibrary ./
# Restore built APK for download/serving:
cp temporary_deleted/backend_apks/gundu_ata_latest.apk backend/staticfiles/apks/
# Restore full android_app (Android + Unity project) to repo root:
mv temporary_deleted/android_app ./
```

This folder is in `.gitignore`, so it is not committed. Keep it locally if you want to retrieve files later.
