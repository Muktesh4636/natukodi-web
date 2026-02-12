#!/bin/bash
# Setup PgBouncer on Database Server (72.61.254.74)
# Run this script on the database server as root

set -e

DB_USER="muktesh"
DB_PASSWORD="muktesh123"
DB_NAME="dice_game"

echo "=== Installing PgBouncer ==="

# Install PgBouncer
apt-get update -qq
apt-get install -y pgbouncer postgresql-client

# Create directories
mkdir -p /var/log/pgbouncer
mkdir -p /var/run/pgbouncer
chown postgres:postgres /var/log/pgbouncer
chown postgres:postgres /var/run/pgbouncer

# Generate MD5 hash for PgBouncer userlist
# Format: md5(password + username)
MD5_HASH=$(echo -n "${DB_PASSWORD}${DB_USER}" | md5sum | awk '{print $1}')

# Create PgBouncer configuration
cat > /etc/pgbouncer/pgbouncer.ini << EOF
[databases]
${DB_NAME} = host=localhost port=5432 dbname=${DB_NAME} user=${DB_USER} password=${DB_PASSWORD}

[pgbouncer]
; Pool settings - CRITICAL for high concurrency
pool_mode = transaction
max_client_conn = 10000
default_pool_size = 50
min_pool_size = 10
reserve_pool_size = 10
reserve_pool_timeout = 5
max_db_connections = 200
max_user_connections = 1000

; Connection settings
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt

; Logging
logfile = /var/log/pgbouncer/pgbouncer.log
pidfile = /var/run/pgbouncer/pgbouncer.pid
admin_users = postgres
stats_users = postgres

; Performance tuning
server_round_robin = 1
ignore_startup_parameters = extra_float_digits,application_name

; Connection timeout
server_connect_timeout = 15
server_login_retry = 15

; Query timeout
query_timeout = 30
query_wait_timeout = 120
EOF

# Create userlist.txt with MD5 hash
cat > /etc/pgbouncer/userlist.txt << EOF
"${DB_USER}" "md5${MD5_HASH}"
EOF

# Set proper permissions
chown postgres:postgres /etc/pgbouncer/pgbouncer.ini
chown postgres:postgres /etc/pgbouncer/userlist.txt
chmod 640 /etc/pgbouncer/pgbouncer.ini
chmod 640 /etc/pgbouncer/userlist.txt

# Update PostgreSQL pg_hba.conf to allow localhost connections
if ! grep -q "host.*all.*all.*127.0.0.1/32.*md5" /etc/postgresql/*/main/pg_hba.conf; then
    echo "host    all             all             127.0.0.1/32            md5" >> /etc/postgresql/18/main/pg_hba.conf
    systemctl reload postgresql
fi

# Update UFW to allow port 6432 from web server
ufw allow from 72.61.254.71 to any port 6432

# Start and enable PgBouncer
systemctl enable pgbouncer
systemctl restart pgbouncer

# Wait a moment for PgBouncer to start
sleep 2

# Check if PgBouncer is running
if systemctl is-active --quiet pgbouncer; then
    echo "=== PgBouncer installed and started successfully ==="
    echo "PgBouncer is listening on port 6432"
    echo "You can test with: psql -h localhost -p 6432 -U ${DB_USER} -d ${DB_NAME}"
else
    echo "ERROR: PgBouncer failed to start. Check logs: journalctl -u pgbouncer"
    exit 1
fi

echo "=== Setup Complete ==="
echo "Next step: Update Django DB_PORT to 6432 in docker-compose.yml"
