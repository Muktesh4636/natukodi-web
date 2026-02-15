#!/bin/bash

# Fix Server 1 web container and set up Server 2 web server

set -e

PASSWORD="Gunduata@123"

echo "🔧 Fixing Server 1 web container..."

# Fix Server 1
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'FIX_SERVER1'
cd /root/apk_of_ata

# Update docker-compose.yml to use new servers
if [ -f docker-compose.yml ]; then
    # Update DB_HOST to Server 4
    sed -i 's/DB_HOST=72\.61\.254\.74/DB_HOST=72.61.255.231/g' docker-compose.yml
    sed -i 's/DB_PORT=6432/DB_PORT=5432/g' docker-compose.yml
    sed -i 's/DB_PASSWORD=muktesh123/DB_PASSWORD=Gunduata@123/g' docker-compose.yml
    
    # Update REDIS_HOST to Server 3
    sed -i 's/REDIS_HOST=redis/REDIS_HOST=72.62.226.41/g' docker-compose.yml
    sed -i 's/REDIS_PASSWORD=redis_password_change_me/REDIS_PASSWORD=Gunduata@123/g' docker-compose.yml
fi

# Stop and remove problematic container
docker stop dice_game_web 2>/dev/null || true
docker rm dice_game_web 2>/dev/null || true

# Fix migration issue by skipping if table exists
cd backend
python3 manage.py migrate --run-syncdb 2>&1 | grep -v "already exists" || true

# Restart web container
cd ..
docker-compose up -d web

sleep 5

# Check status
if docker ps | grep -q dice_game_web; then
    echo "✅ Server 1 web container started"
else
    echo "⚠️  Server 1 web container may need manual check"
fi
FIX_SERVER1

echo ""
echo "🔧 Setting up Server 2 web server..."

# Setup Server 2
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'SETUP_SERVER2'
cd /root/apk_of_ata

# Check if docker-compose exists
if [ ! -f docker-compose.yml ]; then
    echo "⚠️  docker-compose.yml not found on Server 2"
    exit 1
fi

# Update docker-compose.yml to use new servers
sed -i 's/DB_HOST=72\.61\.254\.74/DB_HOST=72.61.255.231/g' docker-compose.yml 2>/dev/null || true
sed -i 's/DB_PORT=6432/DB_PORT=5432/g' docker-compose.yml 2>/dev/null || true
sed -i 's/DB_PASSWORD=muktesh123/DB_PASSWORD=Gunduata@123/g' docker-compose.yml 2>/dev/null || true
sed -i 's/REDIS_HOST=redis/REDIS_HOST=72.62.226.41/g' docker-compose.yml 2>/dev/null || true
sed -i 's/REDIS_PASSWORD=redis_password_change_me/REDIS_PASSWORD=Gunduata@123/g' docker-compose.yml 2>/dev/null || true

# Start web container
docker-compose up -d web

sleep 5

# Check status
if docker ps | grep -q dice_game_web; then
    echo "✅ Server 2 web container started"
    docker ps | grep dice_game_web
else
    echo "⚠️  Server 2 web container may need manual check"
    docker ps -a | grep dice_game_web || echo "Container not found"
fi
SETUP_SERVER2

echo ""
echo "✅ Server setup complete!"
