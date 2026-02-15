#!/bin/bash

# Deployment script for Optimized WebSocket and Timer Engine
# Usage: ./deploy_optimized_engine.sh [server_ip]

SERVER_IP=${1:-"72.61.254.74"}
REMOTE_USER="root"
REMOTE_PASSWORD="Gunduata@123"
REMOTE_PATH="/root/apk_of_ata/backend"

# Check if sshpass is available
if ! command -v sshpass &> /dev/null; then
    echo "⚠️  sshpass not found. Installing or using alternative method..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "On macOS, install sshpass: brew install hudochenkov/sshpass/sshpass"
        echo "Or run the commands manually with password prompt."
        exit 1
    else
        echo "Please install sshpass: sudo apt-get install sshpass"
        exit 1
    fi
fi

export SSHPASS=$REMOTE_PASSWORD

echo "🚀 Deploying optimized engine and WebSocket consumer to $SERVER_IP..."

# 1. Copy files
echo "📤 Copying files..."
sshpass -e scp -o StrictHostKeyChecking=no backend/game_engine_v2.py $REMOTE_USER@$SERVER_IP:$REMOTE_PATH/
sshpass -e scp -o StrictHostKeyChecking=no backend/game/consumers.py $REMOTE_USER@$SERVER_IP:$REMOTE_PATH/game/
sshpass -e scp -o StrictHostKeyChecking=no backend/game/views.py $REMOTE_USER@$SERVER_IP:$REMOTE_PATH/game/
sshpass -e scp -o StrictHostKeyChecking=no backend/game/utils.py $REMOTE_USER@$SERVER_IP:$REMOTE_PATH/game/
sshpass -e scp -o StrictHostKeyChecking=no backend/accounts/views.py $REMOTE_USER@$SERVER_IP:$REMOTE_PATH/accounts/

# 2. Restart services
echo "🔄 Restarting services on $SERVER_IP..."
sshpass -e ssh -o StrictHostKeyChecking=no $REMOTE_USER@$SERVER_IP << 'EOF'
    # Kill old engine if running
    pkill -f game_engine_v2.py || true
    
    # Restart Gunicorn/Daphne (WebSocket consumer)
    cd /root/apk_of_ata || exit 1
    if command -v docker &> /dev/null && docker compose ps &> /dev/null; then
        echo "Restarting via Docker Compose..."
        docker compose restart web
    elif systemctl is-active --quiet gunicorn; then
        echo "Restarting via systemctl..."
        systemctl restart gunicorn
    else
        echo "Manual process restart (pkill gunicorn)..."
        pkill -HUP gunicorn || pkill gunicorn
    fi

    # Start new engine inside the web container
    echo "Starting Game Engine inside web container..."
    docker compose exec -d web python3 game_engine_v2.py
    
    echo "✅ Services restarted."
EOF

echo "✨ Deployment complete!"
