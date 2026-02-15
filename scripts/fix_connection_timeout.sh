#!/bin/bash

# Fix Connection Timeout Issues
# Reduces database connection timeout and optimizes settings

PASSWORD="Gunduata@123"

echo "🔧 FIXING CONNECTION TIMEOUT"
echo "============================"
echo ""

# Update settings.py on both servers
echo "1. Updating connection timeout settings..."

sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'UPDATE_SERVER1'
cd /root/apk_of_ata/backend
if [ -f dice_game/settings.py ]; then
    # Reduce connect_timeout from 120 to 10 seconds
    sed -i "s/'connect_timeout': 120/'connect_timeout': 10/g" dice_game/settings.py
    echo "✅ Server 1: Connection timeout reduced to 10 seconds"
else
    echo "⚠️  settings.py not found on Server 1"
fi
UPDATE_SERVER1

sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'UPDATE_SERVER2'
cd /root/apk_of_ata/backend
if [ -f dice_game/settings.py ]; then
    # Reduce connect_timeout from 120 to 10 seconds
    sed -i "s/'connect_timeout': 120/'connect_timeout': 10/g" dice_game/settings.py
    echo "✅ Server 2: Connection timeout reduced to 10 seconds"
else
    echo "⚠️  settings.py not found on Server 2"
fi
UPDATE_SERVER2

echo ""
echo "2. Restarting containers..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 "cd /root/apk_of_ata && docker compose restart web"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 "cd /root/apk_of_ata && docker compose restart web"

echo ""
echo "✅ Connection timeout fixed!"
echo "   - Reduced from 120s to 10s for faster error detection"
echo "   - Containers restarted"
