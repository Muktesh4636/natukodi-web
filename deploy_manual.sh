#!/bin/bash

# Manual deployment script for OTP fix
# Run this script in your terminal (it will prompt for password)

set -e

SERVER_USER="root"
SERVER_IP="72.61.254.71"
PROJECT_DIR_ON_SERVER="~/apk_of_ata"

echo "=== Manual Deployment Script ==="
echo "This will copy the updated sms_service.py to the server and restart containers"
echo ""

# Step 1: Copy the updated file
echo "Step 1: Copying sms_service.py to server..."
echo "You will be prompted for password: Gunduata@123"
scp backend/accounts/sms_service.py ${SERVER_USER}@${SERVER_IP}:${PROJECT_DIR_ON_SERVER}/backend/accounts/

if [ $? -eq 0 ]; then
    echo "✅ File copied successfully"
else
    echo "❌ Failed to copy file"
    exit 1
fi

# Step 2: SSH and restart containers
echo ""
echo "Step 2: Restarting containers on server..."
echo "You will be prompted for password again: Gunduata@123"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
cd ~/apk_of_ata
echo "Restarting web container..."
docker compose restart web
echo "Waiting for container to start..."
sleep 5
echo "Checking container status..."
docker compose ps
echo "Viewing recent logs..."
docker compose logs --tail=50 web
ENDSSH

echo ""
echo "✅ Deployment complete!"
echo "The OTP verification fix has been deployed."
