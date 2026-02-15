#!/bin/bash

# Configure PgBouncer Architecture for Login
# Mobile App → Nginx Load Balancer → App Server → PgBouncer → PostgreSQL

PASSWORD="Gunduata@123"

echo "🔧 CONFIGURING PGBOUNCER ARCHITECTURE"
echo "====================================="
echo ""
echo "Architecture:"
echo "Mobile App → Nginx LB → App Server (S1/S2) → PgBouncer (S4:6432) → PostgreSQL (S4:5432)"
echo ""

# Update Server 1
echo "1. Updating Server 1 configuration..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'UPDATE_SERVER1'
cd /root/apk_of_ata/backend
if [ -f .env ]; then
    sed -i 's/DB_PORT=5432/DB_PORT=6432/g' .env
    sed -i 's/DB_HOST=.*/DB_HOST=72.61.255.231/g' .env
    echo "✅ Server 1 .env updated:"
    grep -E 'DB_HOST|DB_PORT' .env
else
    echo "⚠️  .env file not found"
fi
UPDATE_SERVER1

# Update Server 2
echo ""
echo "2. Updating Server 2 configuration..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'UPDATE_SERVER2'
cd /root/apk_of_ata
if [ -f docker-compose.yml ]; then
    sed -i 's/DB_PORT=5432/DB_PORT=6432/g' docker-compose.yml
    sed -i 's/DB_HOST=.*/DB_HOST=72.61.255.231/g' docker-compose.yml
    echo "✅ Server 2 docker-compose.yml updated:"
    grep -E 'DB_HOST|DB_PORT' docker-compose.yml | head -2
else
    echo "⚠️  docker-compose.yml not found"
fi
UPDATE_SERVER2

# Verify PgBouncer
echo ""
echo "3. Verifying PgBouncer on Server 4..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.255.231 << 'VERIFY_PGBOUNCER'
echo "PgBouncer status:"
systemctl is-active pgbouncer && echo "✅ PgBouncer is running" || echo "❌ PgBouncer is not running"
echo ""
echo "PgBouncer listening on:"
ss -tlnp | grep 6432 || netstat -tlnp | grep 6432
echo ""
echo "Testing connection via PgBouncer:"
PGPASSWORD=Gunduata@123 psql -h localhost -p 6432 -U muktesh -d dice_game -c 'SELECT version();' 2>&1 | head -2
VERIFY_PGBOUNCER

# Restart containers
echo ""
echo "4. Restarting containers..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 "cd /root/apk_of_ata && docker compose restart web"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 "cd /root/apk_of_ata && docker compose restart web"

echo ""
echo "5. Testing connections..."
sleep 5

echo "Server 1 test:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 << 'TEST_SERVER1'
cd /root/apk_of_ata
docker exec dice_game_web python manage.py shell << 'PYTHON_TEST'
from django.db import connection
cursor = connection.cursor()
cursor.execute('SELECT version()')
print('✅ Server 1 connected via PgBouncer')
PYTHON_TEST
TEST_SERVER1

echo ""
echo "Server 2 test:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.74 << 'TEST_SERVER2'
cd /root/apk_of_ata
docker exec dice_game_web python manage.py shell << 'PYTHON_TEST'
from django.db import connection
cursor = connection.cursor()
cursor.execute('SELECT version()')
print('✅ Server 2 connected via PgBouncer')
PYTHON_TEST
TEST_SERVER2

echo ""
echo "✅ PgBouncer Architecture Configured!"
echo ""
echo "Connection Flow:"
echo "Mobile App → Nginx LB (S1:80) → App Server (S1/S2:8001) → PgBouncer (S4:6432) → PostgreSQL (S4:5432)"
