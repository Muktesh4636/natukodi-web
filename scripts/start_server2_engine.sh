#!/bin/bash
# Simple script to start engine on Server 2

cd /root/apk_of_ata/backend

# Kill any existing
pkill -9 -f game_engine_v3.py 2>/dev/null || true
sleep 2

# Start engine
nohup python3 game_engine_v3.py > engine.log 2>&1 &
echo "Engine started, PID: $!"

sleep 3
tail -15 engine.log
