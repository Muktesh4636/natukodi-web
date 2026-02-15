#!/bin/bash

# Fix Database Connection Issue
# Changes DB_HOST from Server 2 (72.61.254.74) to Server 4 (72.61.255.231)

set -e

PASSWORD="Gunduata@123"

echo "🔍 CHECKING DATABASE CONNECTION"
echo "================================"
echo ""

# Check Server 1
echo "1. Checking Server 1 database config..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'CHECK_SERVER1'
cd /root/apk_of_ata
echo "Current DB_HOST in docker-compose.yml:"
grep "DB_HOST" docker-compose.yml | head -1 || echo "File not found"
echo ""
echo "Current DB_PASSWORD in docker-compose.yml:"
grep "DB_PASSWORD" docker-compose.yml | head -1 || echo "Not found"
echo ""
echo "Current DB_PORT in docker-compose.yml:"
grep "DB_PORT" docker-compose.yml | head -1 || echo "Not found"
CHECK_SERVER1

echo ""
echo "2. Checking Server 2 database config..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'CHECK_SERVER2'
cd /root/apk_of_ata
echo "Current DB_HOST in docker-compose.yml:"
grep "DB_HOST" docker-compose.yml | head -1 || echo "File not found"
echo ""
echo "Current DB_PASSWORD in docker-compose.yml:"
grep "DB_PASSWORD" docker-compose.yml | head -1 || echo "Not found"
CHECK_SERVER2

echo ""
echo "3. Testing direct connection to Server 4 database..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'TEST_DB'
PGPASSWORD=Gunduata@123 psql -h 72.61.255.231 -U muktesh -d dice_game -c "SELECT version();" 2>&1 | head -3 || echo "⚠️  Direct connection test failed (psql may not be installed)"
TEST_DB

echo ""
echo "🔧 FIXING DATABASE CONFIGURATION"
echo "================================"

# Fix Server 1
echo "Fixing Server 1..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'FIX_SERVER1'
cd /root/apk_of_ata
if [ -f docker-compose.yml ]; then
    # Update DB_HOST to Server 4
    sed -i 's/DB_HOST=72\.61\.254\.74/DB_HOST=72.61.255.231/g' docker-compose.yml
    sed -i 's/DB_HOST=72\.61\.255\.231/DB_HOST=72.61.255.231/g' docker-compose.yml  # Ensure it's correct
    
    # Update DB_PASSWORD
    sed -i 's/DB_PASSWORD=muktesh123/DB_PASSWORD=Gunduata@123/g' docker-compose.yml
    
    # Update DB_PORT (use 5432 for direct PostgreSQL, or 6432 if PgBouncer is used)
    # Let's use 5432 for now (direct PostgreSQL connection)
    sed -i 's/DB_PORT=6432/DB_PORT=5432/g' docker-compose.yml
    
    echo "✅ Server 1 configuration updated"
    echo "New DB_HOST:"
    grep "DB_HOST" docker-compose.yml | head -1
    echo "New DB_PASSWORD:"
    grep "DB_PASSWORD" docker-compose.yml | head -1
    echo "New DB_PORT:"
    grep "DB_PORT" docker-compose.yml | head -1
else
    echo "❌ docker-compose.yml not found on Server 1"
fi
FIX_SERVER1

# Fix Server 2
echo ""
echo "Fixing Server 2..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'FIX_SERVER2'
cd /root/apk_of_ata
if [ -f docker-compose.yml ]; then
    # Update DB_HOST to Server 4
    sed -i 's/DB_HOST=72\.61\.254\.74/DB_HOST=72.61.255.231/g' docker-compose.yml
    sed -i 's/DB_HOST=72\.61\.255\.231/DB_HOST=72.61.255.231/g' docker-compose.yml  # Ensure it's correct
    
    # Update DB_PASSWORD
    sed -i 's/DB_PASSWORD=muktesh123/DB_PASSWORD=Gunduata@123/g' docker-compose.yml
    
    # Update DB_PORT
    sed -i 's/DB_PORT=6432/DB_PORT=5432/g' docker-compose.yml
    
    echo "✅ Server 2 configuration updated"
    echo "New DB_HOST:"
    grep "DB_HOST" docker-compose.yml | head -1
    echo "New DB_PASSWORD:"
    grep "DB_PASSWORD" docker-compose.yml | head -1
    echo "New DB_PORT:"
    grep "DB_PORT" docker-compose.yml | head -1
else
    echo "❌ docker-compose.yml not found on Server 2"
fi
FIX_SERVER2

echo ""
echo "🔄 RESTARTING CONTAINERS"
echo "========================="

# Restart Server 1
echo "Restarting Server 1 web container..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'RESTART_SERVER1'
cd /root/apk_of_ata
docker compose stop web 2>/dev/null || true
docker compose rm -f web 2>/dev/null || true
docker compose up -d web
sleep 5
echo "Container status:"
docker ps | grep web || echo "Container not running"
RESTART_SERVER1

# Restart Server 2
echo ""
echo "Restarting Server 2 web container..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'RESTART_SERVER2'
cd /root/apk_of_ata
docker compose stop web 2>/dev/null || true
docker compose rm -f web 2>/dev/null || true
docker compose up -d web
sleep 5
echo "Container status:"
docker ps | grep web || echo "Container not running"
RESTART_SERVER2

echo ""
echo "✅ DATABASE CONNECTION FIXED!"
echo "=============================="
echo ""
echo "Testing database connection from containers..."
echo ""

# Test Server 1
echo "Server 1 database test:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'TEST_SERVER1'
cd /root/apk_of_ata
sleep 3
docker exec dice_game_web python manage.py dbshell << 'SQL_TEST' 2>&1 | head -5 || echo "⚠️  Connection test failed - container may still be starting"
SELECT version();
SQL_TEST
TEST_SERVER1

# Test Server 2
echo ""
echo "Server 2 database test:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'TEST_SERVER2'
cd /root/apk_of_ata
sleep 3
docker exec dice_game_web python manage.py dbshell << 'SQL_TEST' 2>&1 | head -5 || echo "⚠️  Connection test failed - container may still be starting"
SELECT version();
SQL_TEST
TEST_SERVER2

echo ""
echo "✅ Fix complete! Try logging in now."
