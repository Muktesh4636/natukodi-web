#!/bin/bash

# ==============================================================================
# Gundu Ata - Unified Deployment Script
# ==============================================================================
# This script deploys the latest backend changes to all production servers.
# It handles git synchronization, environment updates, and Docker restarts.
# ==============================================================================

# Configuration
PASSWORD="Gunduata@123"
SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")
REMOTE_DIR="/root/apk_of_ata"

echo "🚀 Starting deployment to ${#SERVERS[@]} servers..."
echo "Current Time: $(date)"

# Loop through each server
for SERVER in "${SERVERS[@]}"; do
    echo ""
    echo "----------------------------------------------------------------------"
    echo "🌐 Processing Server: $SERVER"
    echo "----------------------------------------------------------------------"
    
    # Execute commands on the remote server
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER << EOF
        echo "📂 Navigating to project directory: $REMOTE_DIR"
        cd $REMOTE_DIR || { echo "❌ Error: Directory $REMOTE_DIR not found on $SERVER"; exit 1; }
        
        # 1. Clean local state
        echo "🧹 Cleaning local git state..."
        git reset --hard
        git clean -fd
        
        # 2. Pull latest changes
        echo "📥 Pulling latest changes from master..."
        git pull origin master
        
        # 3. Server-specific fixes
        # Server 3 (72.62.226.41) is the dedicated Redis host
        if [ "$SERVER" == "72.62.226.41" ]; then
            echo "🔧 Applying Redis port fix for Server 3..."
            systemctl stop redis-server 2>/dev/null || true
            systemctl disable redis-server 2>/dev/null || true
        fi
        
        # 4. Restart Docker Services
        echo "🔄 Restarting Docker containers..."
        # down --remove-orphans ensures a clean state
        docker compose down --remove-orphans
        
        # up -d starts services in background
        docker compose up -d
        
        echo "✅ Server $SERVER update successful."
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
EOF

    if [ $? -eq 0 ]; then
        echo "✨ Finished Server $SERVER"
    else
        echo "❌ Failed to update Server $SERVER"
    fi
done

echo ""
echo "======================================================================"
echo "🎉 Deployment Complete for all servers!"
echo "======================================================================"

# Final health check on the primary load balancer
echo "🔍 Performing health check on Load Balancer (72.61.254.71)..."
sleep 5
curl -s -I http://72.61.254.71/api/auth/leaderboard/ | grep "HTTP" || echo "⚠️ Load balancer health check failed or timed out."

echo "📝 Monitoring logs on Server 1 (72.61.254.71) for errors..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 "docker logs --tail 20 dice_game_web"
