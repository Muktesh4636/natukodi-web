#!/bin/bash

# Script to clean up old timers and start the new game engine architecture
# Run this on Server 1 and Server 2

set -e

echo "🔧 Cleaning up old timers and starting new architecture..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKEND_DIR="/root/apk_of_ata/backend"
ENGINE_LOG="$BACKEND_DIR/engine.log"

# Function to print colored messages
print_info() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Step 1: Stop old Docker timer container
print_info "Stopping old Docker timer container..."
if docker ps | grep -q dice_game_timer; then
    docker stop dice_game_timer
    print_info "Old timer container stopped"
else
    print_warning "Old timer container not running"
fi

# Step 2: Kill all game_engine_v3.py processes
print_info "Stopping all game_engine_v3.py processes..."
pkill -f "game_engine_v3.py" || print_warning "No game_engine_v3.py processes found"
sleep 2

# Verify they're stopped
if pgrep -f "game_engine_v3.py" > /dev/null; then
    print_error "Some game_engine_v3.py processes are still running. Force killing..."
    pkill -9 -f "game_engine_v3.py"
    sleep 1
fi

# Step 3: Stop old Django timer if running
print_info "Stopping old Django start_game_timer processes..."
pkill -f "start_game_timer" || print_warning "No start_game_timer processes found"
sleep 1

# Step 4: Clear old engine log
print_info "Clearing old engine log..."
> "$ENGINE_LOG"

# Step 5: Check Redis connectivity
print_info "Checking Redis connectivity..."
cd "$BACKEND_DIR"

# Source virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Test Redis connection
python3 << EOF
import redis
import os
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
import django
django.setup()

try:
    r = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5
    )
    r.ping()
    print("✅ Redis connection successful")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
    exit(1)
EOF

if [ $? -ne 0 ]; then
    print_error "Redis connection failed. Please check Redis server."
    exit 1
fi

# Step 6: Start new game engine
print_info "Starting new game engine (game_engine_v3.py)..."
cd "$BACKEND_DIR"

# Start engine in background with nohup
nohup python3 game_engine_v3.py > engine.log 2>&1 &
ENGINE_PID=$!

sleep 3

# Check if engine started successfully
if ps -p $ENGINE_PID > /dev/null; then
    print_info "Game engine started successfully (PID: $ENGINE_PID)"
else
    print_error "Game engine failed to start. Check engine.log for errors:"
    tail -20 "$ENGINE_LOG"
    exit 1
fi

# Step 7: Verify engine is acquiring lock
print_info "Waiting for engine to acquire lock..."
sleep 5

# Check Redis lock
python3 << EOF
import redis
import os
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dice_game.settings')
import django
django.setup()

try:
    r = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        decode_responses=True
    )
    lock_value = r.get('game_engine_lock')
    if lock_value:
        print(f"✅ Lock acquired by instance: {lock_value}")
        ttl = r.ttl('game_engine_lock')
        print(f"✅ Lock TTL: {ttl} seconds")
    else:
        print("⚠️  Lock not acquired yet. Engine may still be starting...")
    
    # Check game state
    state = r.get('current_game_state')
    if state:
        print("✅ Game state found in Redis")
    else:
        print("⚠️  No game state in Redis yet")
except Exception as e:
    print(f"❌ Error checking Redis: {e}")
EOF

# Step 8: Show recent logs
print_info "Recent engine logs:"
tail -10 "$ENGINE_LOG"

print_info ""
print_info "🎮 Setup complete!"
print_info "Monitor the engine with: tail -f $ENGINE_LOG"
print_info "Check Redis lock with: redis-cli -a Gunduata@123 GET game_engine_lock"
