#!/usr/bin/env bash
# Export Unity project for Android (Gradle/unityLibrary) via command line.
# Requires Unity 6000.3.8f1 (or compatible) installed via Unity Hub.
#
# Usage:
#   ./export_unity_android.sh [output_dir]
#
# Examples:
#   ./export_unity_android.sh                    # exports to android_app/unityExport
#   ./export_unity_android.sh /tmp/unityOut       # exports to /tmp/unityOut
#
# After export, copy unityLibrary to android_app:
#   cp -R unityExport/unityLibrary android_app/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITY_PROJECT="${SCRIPT_DIR}/unity/DiceGame"
DEFAULT_OUTPUT="${SCRIPT_DIR}/unityExport"
OUTPUT_DIR="${1:-$DEFAULT_OUTPUT}"

# Unity executable - try common paths or UNITY_PATH env
find_unity() {
    if [[ -n "$UNITY_PATH" && -x "$UNITY_PATH" ]]; then
        echo "$UNITY_PATH"
        return
    fi
    local candidates=(
        "/Applications/Unity/Hub/Editor/6000.3.8f1/Unity.app/Contents/MacOS/Unity"
        "/Applications/Unity/Unity.app/Contents/MacOS/Unity"
    )
    for p in "${candidates[@]}"; do
        if [[ -x "$p" ]]; then
            echo "$p"
            return
        fi
    done
    # Try 'unity' in PATH (Unity Hub CLI)
    if command -v unity &>/dev/null; then
        echo "unity"
        return
    fi
    echo ""
}

UNITY_EXE=$(find_unity)
if [[ -z "$UNITY_EXE" ]]; then
    echo "Unity not found. Install Unity 6000.3.8f1 via Unity Hub, or set UNITY_PATH."
    echo "  export UNITY_PATH=/Applications/Unity/Hub/Editor/6000.3.8f1/Unity.app/Contents/MacOS/Unity"
    exit 1
fi

if [[ ! -d "$UNITY_PROJECT" ]]; then
    echo "Unity project not found: $UNITY_PROJECT"
    exit 1
fi

echo "Unity: $UNITY_EXE"
echo "Project: $UNITY_PROJECT"
echo "Output: $OUTPUT_DIR"
echo ""

mkdir -p "$OUTPUT_DIR"
LOG_FILE="${OUTPUT_DIR}/unity_export.log"

echo "Starting Unity batch export (this may take several minutes)..."
if "$UNITY_EXE" -batchmode -quit \
    -projectPath "$UNITY_PROJECT" \
    -executeMethod AndroidExportBuild.ExportAndroidProject \
    -exportPath "$OUTPUT_DIR" \
    -logFile "$LOG_FILE"; then
    echo "Export succeeded."
    if [[ -d "${OUTPUT_DIR}/unityLibrary" ]]; then
        echo ""
        echo "To update android_app with the new unityLibrary:"
        echo "  cp -R ${OUTPUT_DIR}/unityLibrary ${SCRIPT_DIR}/unityLibrary"
        echo "  cd ${SCRIPT_DIR} && ./gradlew assembleRelease -PskipIl2CppBuild"
    fi
else
    EXIT_CODE=$?
    echo "Export failed (exit $EXIT_CODE). Check log: $LOG_FILE"
    tail -100 "$LOG_FILE" 2>/dev/null || true
    exit $EXIT_CODE
fi
