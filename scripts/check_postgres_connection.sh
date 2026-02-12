#!/bin/bash

# Script to check PostgreSQL connection and current max_connections
# This can be run from the web server

set -e

# Configuration from docker-compose.yml
DB_HOST="72.61.254.74"
DB_USER="muktesh"
DB_PASSWORD="muktesh123"
DB_NAME="dice_game"
DB_PORT="5432"

echo "=========================================="
echo "PostgreSQL Connection Check"
echo "=========================================="
echo ""

echo "Attempting to connect to PostgreSQL at $DB_HOST:$DB_PORT"
echo ""

# Check if we can connect and get max_connections
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SHOW max_connections;" 2>&1 || {
    echo ""
    echo "Could not connect to PostgreSQL directly."
    echo ""
    echo "To increase max_connections, you need to:"
    echo ""
    echo "1. SSH into the PostgreSQL server ($DB_HOST)"
    echo "2. Edit PostgreSQL config:"
    echo "   sudo nano /etc/postgresql/*/main/postgresql.conf"
    echo "3. Change: max_connections = 200"
    echo "4. Restart: sudo systemctl restart postgresql"
    echo ""
    echo "OR if PostgreSQL is managed (AWS RDS, etc.):"
    echo "- Use your cloud provider's console to modify database parameters"
    echo ""
}
