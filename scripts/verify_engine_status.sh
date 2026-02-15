#!/bin/bash

# Script to verify game engine status across all servers

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo "🔍 Checking Game Engine Status..."
echo ""

# Check Server 1
echo "📡 Server 1 (72.61.254.71):"
sshpass -p 'Gunduata@123' ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'EOF'
echo "  Processes:"
ps aux | grep -E 'game_engine_v3|start_game_timer' | grep -v grep | awk '{print "    PID:", $2, "CPU:", $3"%", "CMD:", $11, $12, $13}' || echo "    No game engine processes found"

echo "  Docker Timer:"
docker ps | grep timer | awk '{print "    Container:", $1, "Status:", $7}' || echo "    No timer container running"

echo "  Engine Log (last 5 lines):"
if [ -f /root/apk_of_ata/backend/engine.log ]; then
    tail -5 /root/apk_of_ata/backend/engine.log | sed 's/^/    /'
else
    echo "    No engine.log found"
fi
EOF

echo ""
echo "📡 Redis Server (72.62.226.41):"
sshpass -p 'Gunduata@123' ssh -o StrictHostKeyChecking=no root@72.62.226.41 << 'EOF'
echo "  Redis Lock:"
LOCK=$(redis-cli -a Gunduata@123 GET game_engine_lock 2>/dev/null)
if [ -z "$LOCK" ]; then
    echo "    ⚠️  No lock acquired"
else
    TTL=$(redis-cli -a Gunduata@123 TTL game_engine_lock 2>/dev/null)
    echo "    ✅ Lock held by: $LOCK (TTL: $TTL seconds)"
fi

echo "  Game State:"
STATE=$(redis-cli -a Gunduata@123 GET current_game_state 2>/dev/null)
if [ -z "$STATE" ]; then
    echo "    ⚠️  No game state in Redis"
else
    echo "    ✅ Game state exists (length: ${#STATE} chars)"
fi

echo "  Timer:"
TIMER=$(redis-cli -a Gunduata@123 GET round_timer 2>/dev/null)
if [ -z "$TIMER" ]; then
    echo "    ⚠️  No timer value"
else
    echo "    ✅ Timer: $TIMER seconds"
fi
EOF

echo ""
print_info "Status check complete!"
