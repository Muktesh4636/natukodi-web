#!/bin/bash

# Build script for Unity WebGL
# This script assumes Unity is installed and accessible via command line

UNITY_PROJECT_PATH="android_app/DiceGame-1.0/DiceGame"
BUILD_OUTPUT_PATH="$UNITY_PROJECT_PATH/Builds/WebGL"

echo "Building Unity project for WebGL..."

# Create output directory
mkdir -p "$BUILD_OUTPUT_PATH"

# Unity command line build
# Note: You need to replace the path to Unity executable with your actual path
UNITY_EXECUTABLE="/Applications/Unity/Hub/Editor/2022.3.16f1/Unity.app/Contents/MacOS/Unity"  # macOS example
# For Windows: "C:\Program Files\Unity\Hub\Editor\2022.3.16f1\Editor\Unity.exe"
# For Linux: "/opt/unity/Editor/Unity"

if [ ! -f "$UNITY_EXECUTABLE" ]; then
    echo "Unity executable not found at $UNITY_EXECUTABLE"
    echo "Please update the UNITY_EXECUTABLE path in this script to match your Unity installation"
    exit 1
fi

# Run Unity build
"$UNITY_EXECUTABLE" \
  -batchmode \
  -nographics \
  -projectPath "$UNITY_PROJECT_PATH" \
  -executeMethod BuildScript.BuildWebGL \
  -quit \
  -logFile build.log

if [ $? -eq 0 ]; then
    echo "WebGL build completed successfully!"
    echo "Build output: $BUILD_OUTPUT_PATH"

    # Copy build files to backend static folder
    BACKEND_STATIC_PATH="backend/static/unity"
    mkdir -p "$BACKEND_STATIC_PATH"
    cp -r "$BUILD_OUTPUT_PATH"/* "$BACKEND_STATIC_PATH"/

    echo "Build files copied to backend static folder: $BACKEND_STATIC_PATH"
else
    echo "Build failed. Check build.log for details."
    exit 1
fi