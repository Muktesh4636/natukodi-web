#!/usr/bin/env bash
# 1) Build WebGL with Unity (batch mode). Close Unity Editor first.
# 2) Serve the build at http://localhost:8080

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
UNITY="/Applications/Unity/Hub/Editor/6000.3.8f1/Unity.app/Contents/MacOS/Unity"

echo "Building WebGL (close Unity Editor if this project is open)..."
if ! "$UNITY" -quit -batchmode -projectPath "$SCRIPT_DIR" -executeMethod BuildWebGL.BuildFromCommandLine -logFile /tmp/unity_webgl_build.log; then
  if grep -q "another Unity instance" /tmp/unity_webgl_build.log 2>/dev/null; then
    echo "Close the Unity Editor (this project open), then run this script again."
  else
    echo "Build failed. See /tmp/unity_webgl_build.log"
  fi
  exit 1
fi

BUILD_DIR="$SCRIPT_DIR/Builds/WebGL"
if [ ! -d "$BUILD_DIR" ]; then
  echo "Build did not produce Builds/WebGL."
  exit 1
fi
cd "$BUILD_DIR"
PORT="${1:-8080}"
echo "Serving at http://localhost:$PORT — open in browser (Ctrl+C to stop)."
echo "If you see 'Address already in use', run: $0 8081"
python3 -m http.server "$PORT"
