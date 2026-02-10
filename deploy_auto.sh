#!/bin/bash

# Automated deployment script using sshpass
# Usage: ./deploy_auto.sh

set -e

# Configuration
SERVER_USER="root"
SERVER_IP="72.61.254.71"
SERVER_PASS="Gunduata@123"
PROJECT_DIR_ON_SERVER="~/apk_of_ata"
LOCAL_BACKEND_DIR="./backend"
LOCAL_DOCKER_COMPOSE_FILE="docker-compose.yml"

echo "=== Automated Deployment to Server ==="

# Step 1: Copy docker-compose.yml
echo "Step 1/3: Copying docker-compose.yml..."
sshpass -p "$SERVER_PASS" scp -o StrictHostKeyChecking=no "$LOCAL_DOCKER_COMPOSE_FILE" "$SERVER_USER@$SERVER_IP:$PROJECT_DIR_ON_SERVER/"

# Step 2: Copy backend directory
echo "Step 2/3: Copying backend directory..."
# Using rsync with sshpass for efficiency
sshpass -p "$SERVER_PASS" rsync -avz -e "ssh -o StrictHostKeyChecking=no" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='venv' \
    --exclude='.env' \
    --exclude='db.sqlite3' \
    --exclude='staticfiles' \
    "$LOCAL_BACKEND_DIR/" "$SERVER_USER@$SERVER_IP:$PROJECT_DIR_ON_SERVER/backend/"

# Step 3: Restart containers on server
echo "Step 3/3: Restarting containers on server..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << ENDSSH
    cd $PROJECT_DIR_ON_SERVER
    docker compose down
    docker compose up -d --build
    echo "Deployment successful. Container status:"
    docker compose ps
ENDSSH

echo "=== Deployment Complete ==="
