# Unused Files in Repository

These files are **not referenced** by the running app, URLs, or deploy scripts. **They have been moved to `temporary_deleted/`** (not permanently deleted) so you can retrieve them anytime. The **only** game engine in use is `backend/game_engine_v2.py`; the app uses `backend/accounts/views.py` and `backend/game/admin_views.py`.

---

## Backend duplicate/unused (moved to temporary_deleted/backend_duplicates/)

| File | Reason |
|------|--------|
| `backend/game/admin_views_server.py` | Duplicate of `admin_views.py`; URLs use `admin_views` only |
| `backend/game_engine.py` | Legacy engine; app uses `game_engine_v2.py` or `game_engine_v3.py` |
| `backend/websocket_server.py` | Unused; WebSockets use Django Channels `game/consumers.py` |
| `backend/test_migrate.py` | One-off test script |
| Root `settings.py` | Duplicate; Django uses `backend/dice_game/settings.py` |

**Note:** `backend/game/consumers_v2.py` is still in the repo because `tools/deploy_all.sh` copies it; the app’s routing uses `consumers.py` only. If you stop using that deploy script, you can move `consumers_v2.py` to `temporary_deleted/backend_duplicates/` too.

**Templates (moved to temporary_deleted/backend_duplicates/templates_admin/):** `withdraw_requests_server.html`, `transactions_server.html`, `_sidebar_menu_server.html` — views render `withdraw_requests.html`, `transactions.html`, and include `_sidebar_menu.html`; the `_server` variants were never used.

---

## Root directory – unused (safe to untrack/delete)

| File | Reason |
|------|--------|
| `accounts_views_fixed.py` | Old copy; app uses `backend/accounts/views.py` |
| `accounts_views_server.py` | Old copy; only used as input by `fix_withdraw.py` |
| `admin_views_server1.py` | Old copy; app uses `backend/game/admin_views.py` |
| `authentication.py` | Duplicate; app uses `backend/dice_game/authentication.py` |
| `fix_case_conflicts.py` | One-off script |
| `fix_withdraw.py` | One-off script (reads/writes the accounts_views copies above) |
| `game_engine_v2.py` | Root copy unused; deploy uses `backend/game_engine_v2.py` |
| `game_engine_v2_clean.py` | Old variant, never referenced |
| `game_engine_v2_current.py` | Old variant |
| `game_engine_v2_final.py` | Old variant |
| `game_engine_v2_fixed.py` | Old variant |
| `game_engine_v2_latest.py` | Old variant |
| `game_engine_v2_local.py` | Old variant |
| `game_engine_v2_logic.py` | Old variant |
| `game_engine_v2_new_types.py` | Old variant |
| `game_engine_v2_optimized.py` | Old variant |
| `game_engine_v2_ordered.py` | Old variant |
| `game_engine_v2_temp.py` | Old variant |
| `game_engine_v2_updated.py` | Old variant |

---

## android_app/ – debug/fix copies and logs (not part of build)

These sit next to the real app (`android_app/app/`, `android_app/unityLibrary/`) and are **not** used by the Android build. Many are one-off debug copies or logs.

- `android_app/*.py` – e.g. `accounts_views_*`, `admin_*`, `fix_*.py`, `backend_*.py`, `models_*.py`, `views_*.py`, `urls_*.py`, `serializers_*.py`, `server_views.py`
- `android_app/*.txt` – e.g. `crash_log.txt`, `*_dump.txt`, `*_logs*.txt`, `logcat.txt`
- `android_app/android_app/` – nested duplicate path; contains `logcat.txt`, `.cxx/` build artifacts, unity crash logs
- `android_app/unityLibrary/.cxx/` – build artifacts (should be in .gitignore)
- `android_app/stream_test_output/` – test output

The real app code is under `android_app/app/` and `android_app/unityLibrary/src/` (and Unity project under `android_app/unity/`).

---

## Already listed in previous cleanup (video, logs, reports, screenshots)

- `video/` (e.g. `VIDEO-2026-01-25-20-17-48.mp4`)
- `deposit_screenshots_s1/`, `deposit_screenshots_s3/`, `screenshot_*.jpg`
- `big_logs.txt`, `full_logs_debug.txt`, `unity_*.txt`, `locust_report*.html`, `bet_load_test_report.html`
- `Message_Central_SDK_Verify_Now_Doc.pdf` (optional: move to `docs/` or remove from repo)

---

## Optional: keep for reference

- `fix_redis_config.sh` – ops/setup script
- `DiceGamePage.tsx`, `web_dice_game_component.tsx` – doc/sample for WebGL (referenced in docs)
- `settings.py` (root) – may be used by some scripts; confirm before removing

---

## How to untrack (files stay on disk, removed from git)

Run from repo root:

```bash
# Root unused Python
git rm --cached accounts_views_fixed.py accounts_views_server.py admin_views_server1.py authentication.py fix_case_conflicts.py fix_withdraw.py 2>/dev/null || true
git rm --cached game_engine_v2.py game_engine_v2_clean.py game_engine_v2_current.py game_engine_v2_final.py game_engine_v2_fixed.py game_engine_v2_latest.py game_engine_v2_local.py game_engine_v2_logic.py game_engine_v2_new_types.py game_engine_v2_optimized.py game_engine_v2_ordered.py game_engine_v2_temp.py game_engine_v2_updated.py 2>/dev/null || true

# Then commit
git add .gitignore docs/UNUSED_FILES.md
git commit -m "Untrack unused root copies and document unused files"
```

To also untrack android_app debug/fix files and logs, run (review list first):

```bash
git ls-files 'android_app/*.py' 'android_app/*.txt' 'android_app/android_app/' 'android_app/stream_test_output/' 'android_app/unityLibrary/.cxx/' | while read f; do git rm --cached "$f" 2>/dev/null || true; done
```

Then add/commit. After that, add appropriate entries to `.gitignore` so these paths are not re-added (see next section).
