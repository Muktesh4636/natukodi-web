#!/bin/bash

# Deployment script with password authentication
# Usage: ./deploy_now.sh

set -e

SERVER_USER="root"
SERVER_IP="72.61.254.71"
SERVER_PASSWORD="Gunduata@123"
PROJECT_DIR="/root/apk_of_ata"
BACKEND_DIR="./backend"

echo "🚀 Deploying to server ${SERVER_USER}@${SERVER_IP}..."
echo ""

# Check if sshpass is installed
if ! command -v sshpass &> /dev/null; then
    echo "⚠️  sshpass not found. Installing..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install hudochenkov/sshpass/sshpass 2>/dev/null || {
            echo "Please install sshpass manually: brew install hudochenkov/sshpass/sshpass"
            exit 1
        }
    else
        sudo apt-get update && sudo apt-get install -y sshpass 2>/dev/null || {
            echo "Please install sshpass manually: sudo apt-get install sshpass"
            exit 1
        }
    fi
fi

# Function to run command on server
run_on_server() {
    sshpass -p "${SERVER_PASSWORD}" ssh -o StrictHostKeyChecking=no ${SERVER_USER}@${SERVER_IP} "$1"
}

# Function to copy file to server
copy_to_server() {
    sshpass -p "${SERVER_PASSWORD}" scp -o StrictHostKeyChecking=no "$1" ${SERVER_USER}@${SERVER_IP}:"$2"
}

# Step 1: Copy backend directory and docker-compose.yml
echo "📦 Step 1/4: Copying code and config to server..."
rsync -avz --progress \
    -e "sshpass -p '${SERVER_PASSWORD}' ssh -o StrictHostKeyChecking=no" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='venv' \
    --exclude='db.sqlite3' \
    --exclude='*.log' \
    --exclude='staticfiles' \
    --exclude='media' \
    ${BACKEND_DIR}/ ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR}/backend/ || {
    echo "❌ Failed to copy backend directory"
    exit 1
}

copy_to_server "docker-compose.yml" "${PROJECT_DIR}/docker-compose.yml" || {
    echo "❌ Failed to copy docker-compose.yml"
    exit 1
}

# Step 2: Pull latest code from git on server
echo ""
echo "📥 Step 2/4: Pulling latest code from git..."
run_on_server "cd ${PROJECT_DIR}/backend && git pull origin master || git pull origin main"

# Step 3: Run migrations
echo ""
echo "🗄️  Step 3/4: Running database migrations..."
run_on_server "cd ${PROJECT_DIR}/backend && docker exec -it dice_game_web python manage.py migrate accounts || (cd ${PROJECT_DIR} && docker compose exec web python manage.py migrate accounts)"

# Step 4: Restart services
echo ""
echo "🔄 Step 4/4: Applying changes and restarting Docker services..."
run_on_server "cd ${PROJECT_DIR} && docker compose up -d web || docker compose restart web"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Checking service status..."
run_on_server "cd ${PROJECT_DIR} && docker compose ps || docker ps | grep dice_game"

echo ""
echo "🎉 All done! Your changes are now live on the server."
