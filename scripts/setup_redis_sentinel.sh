#!/bin/bash

# Setup Redis Sentinel on all 3 servers
# Server 1, 2, and 3 will run Sentinel

echo "🔧 Setting up Redis Sentinel..."

# Configuration
REDIS_MASTER_IP="72.62.226.41"
REDIS_MASTER_PORT="6379"
REDIS_PASSWORD="Gunduata@123"
SENTINEL_PORT="26379"
MASTER_NAME="mymaster"

# Function to setup Sentinel on a server
setup_sentinel() {
    local SERVER=$1
    local SERVER_NAME=$2
    
    echo ""
    echo "📡 Setting up Sentinel on $SERVER_NAME ($SERVER)..."
    
    sshpass -p "$REDIS_PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER << SENTINEL_SETUP
# Install Redis Sentinel if not installed
if ! command -v redis-sentinel &> /dev/null; then
    apt-get update -qq
    apt-get install -y redis-sentinel redis-tools > /dev/null 2>&1
fi

# Create Sentinel config
cat > /etc/redis/sentinel.conf << EOF
port $SENTINEL_PORT
bind 0.0.0.0
protected-mode no

# Monitor the master
sentinel monitor $MASTER_NAME $REDIS_MASTER_IP $REDIS_MASTER_PORT 2
sentinel auth-pass $MASTER_NAME $REDIS_PASSWORD

# Timing
sentinel down-after-milliseconds $MASTER_NAME 5000
sentinel failover-timeout $MASTER_NAME 10000
sentinel parallel-syncs $MASTER_NAME 1

# Logging
loglevel notice
logfile /var/log/redis/sentinel.log
EOF

# Create log directory
mkdir -p /var/log/redis
chown redis:redis /var/log/redis 2>/dev/null || true

# Start Sentinel
systemctl stop redis-sentinel 2>/dev/null || true
systemctl enable redis-sentinel
systemctl start redis-sentinel

sleep 2

# Check status
if systemctl is-active --quiet redis-sentinel; then
    echo "✅ Sentinel started on $SERVER_NAME"
    redis-cli -p $SENTINEL_PORT SENTINEL masters
else
    echo "❌ Sentinel failed to start on $SERVER_NAME"
    systemctl status redis-sentinel --no-pager | tail -10
fi
SENTINEL_SETUP
}

# Setup on Server 1
setup_sentinel "72.61.254.71" "Server 1"

# Setup on Server 2  
setup_sentinel "72.61.254.74" "Server 2"

# Setup on Server 3 (Redis Master)
setup_sentinel "72.62.226.41" "Server 3"

echo ""
echo "✅ Redis Sentinel setup complete!"
echo ""
echo "To verify, run on any server:"
echo "  redis-cli -p 26379 SENTINEL masters"
