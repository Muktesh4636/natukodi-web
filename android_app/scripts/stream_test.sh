#!/bin/bash
# Stream test: Launch app, tap Gundu Ata, capture logcat to find issues

set -e
cd "$(dirname "$0")/.."
OUTPUT_DIR="$(pwd)/stream_test_output"
mkdir -p "$OUTPUT_DIR"
LOGFILE="$OUTPUT_DIR/stream_test_$(date +%Y%m%d_%H%M%S).log"

echo "=== Sikwin Stream Test ===" | tee "$LOGFILE"
echo "Output: $LOGFILE" | tee -a "$LOGFILE"

# 1. Ensure app is running
echo "[1/5] Launching app..." | tee -a "$LOGFILE"
adb shell am force-stop com.sikwin.app 2>/dev/null || true
sleep 1
adb shell am start -n com.sikwin.app/.MainActivity 2>/dev/null
sleep 4

# 2. Clear logcat
echo "[2/5] Clearing logcat..." | tee -a "$LOGFILE"
adb logcat -c 2>/dev/null || true

# 3. Tap Gundu Ata (bottom nav center: 720,2914)
echo "[3/5] Tapping Gundu Ata..." | tee -a "$LOGFILE"
adb shell input tap 720 2914
sleep 2

# 4. Capture logcat for 12 seconds
echo "[4/5] Streaming logcat for 12s..." | tee -a "$LOGFILE"
adb logcat -v time -d 2>/dev/null > "$OUTPUT_DIR/logcat_raw.txt" &
LOGCAT_PID=$!
sleep 12
kill $LOGCAT_PID 2>/dev/null || true

# 5. Analyze
echo "[5/5] Analyzing..." | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"
echo "=== RELEVANT LOGS (sikwin, Unity, game, errors) ===" | tee -a "$LOGFILE"
grep -iE "sikwin|unity|dicegame|UnityPlayer|GameActivity|libgame|libil2cpp|FATAL|AndroidRuntime|AppNavigation|GunduAta|GameManager|Launching|Error|Exception|crash|freeze" "$OUTPUT_DIR/logcat_raw.txt" 2>/dev/null | tail -150 >> "$LOGFILE" || echo "(no matches)" >> "$LOGFILE"

echo "" | tee -a "$LOGFILE"
echo "=== FOCUSED APP (com.sikwin.app) ===" | tee -a "$LOGFILE"
adb shell "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'" 2>/dev/null >> "$LOGFILE" || true

echo "" | tee -a "$LOGFILE"
echo "=== DONE ===" | tee -a "$LOGFILE"
echo "Full log: $LOGFILE"
echo "Raw logcat: $OUTPUT_DIR/logcat_raw.txt"
cat "$LOGFILE"
