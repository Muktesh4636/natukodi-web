#!/bin/bash

sshpass -p 'Gunduata@123' ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'START_SCRIPT'
cd /root/apk_of_ata/backend

# Kill any existing engines
pkill -9 -f game_engine_v3.py || true
sleep 2

# Clear log
> engine.log

# Start with proper environment
source venv/bin/activate
nohup python3 game_engine_v3.py > engine.log 2>&1 &
ENGINE_PID=$!

echo "Engine started with PID: $ENGINE_PID"
sleep 5

# Check if still running
if ps -p $ENGINE_PID > /dev/null; then
    echo "✅ Engine is running"
    echo ""
    echo "Recent logs:"
    tail -30 engine.log
else
    echo "❌ Engine crashed. Error log:"
    cat engine.log
fi

START_SCRIPT
