#!/bin/bash

# Manual deployment script for Gundu Ata
# Usage: ./scripts/deploy_manual.sh

SERVER_IP="${DEPLOY_SERVER_IP:-72.61.254.71}"
SERVER_USER="${DEPLOY_SERVER_USER:-root}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/dice_game}"

# Never commit real credentials — set locally: export DEPLOY_SSH_PASS='...'
if [ -z "${DEPLOY_SSH_PASS:-}" ]; then
  echo "Set DEPLOY_SSH_PASS (SSH password for sshpass) before running this script." >&2
  exit 1
fi

echo "🚀 Starting Manual Deployment to $SERVER_IP..."

# 1. Create deployment directory on server
echo "📁 Creating deployment directory on server..."
sshpass -p "$DEPLOY_SSH_PASS" ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP "mkdir -p $DEPLOY_DIR"

# 2. Sync files using rsync
# Excluding venv, node_modules, .git, and build artifacts to keep it fast
echo "🔄 Syncing files to server..."
sshpass -p "$DEPLOY_SSH_PASS" rsync -avz -e "ssh -o StrictHostKeyChecking=no" \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='.env*' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='android_app/app/build' \
    ./ $SERVER_USER@$SERVER_IP:$DEPLOY_DIR/

# 3. Start services on server
echo "🐳 Cleaning up and starting Docker services on server..."
sshpass -p "$DEPLOY_SSH_PASS" ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP "cd $DEPLOY_DIR && docker compose down --remove-orphans && docker rm -f dice_game_redis dice_game_web dice_game_game_timer || true && docker compose up -d --build"

# 4. Run migrations on server
echo "🗄️ Running database migrations on server..."
# Wait for DB to be ready
sleep 10
sshpass -p "$DEPLOY_SSH_PASS" ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP "cd $DEPLOY_DIR && docker compose exec -T web python manage.py migrate"

echo "✅ Manual Deployment Complete!"
echo "🌐 Check: http://$SERVER_IP:8001/"
