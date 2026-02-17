#!/bin/bash

# Script to deploy the latest changes to all servers and fix common issues

PASSWORD="Gunduata@123"
SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")

echo "🚀 Deploying latest changes to all servers..."

for SERVER in "${SERVERS[@]}"; do
    echo "--------------------------------------------------"
    echo "📦 Processing Server: $SERVER"
    
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER << EOF
        cd /root/apk_of_ata
        
        # Discard any local changes and untracked files to ensure a clean pull
        echo "Discarding local changes and untracked files..."
        git reset --hard
        git clean -fd

        echo "Pulling latest changes from git..."
        git pull origin master
        
        # Fix for "address already in use" on Server 3 (72.62.226.41)
        if [ "$SERVER" == "72.62.226.41" ]; then
            echo "Stopping native redis-server to free up port 6379..."
            systemctl stop redis-server || true
            systemctl disable redis-server || true
        fi

        echo "Restarting Docker services..."
        # Ensure services are recreated to pick up new code and environment variables
        docker compose down --remove-orphans
        docker compose up -d
        
        echo "✅ Server \$SERVER updated and services restarted."
EOF
done

echo "--------------------------------------------------"
echo "🎉 Deployment complete!"
echo "Monitoring logs on Server 72.61.254.71 for 10 seconds..."
sleep 10
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 "docker logs --tail 50 dice_game_web"
