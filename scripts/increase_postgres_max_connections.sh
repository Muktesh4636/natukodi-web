#!/bin/bash

# Script to increase PostgreSQL max_connections
# This fixes the "too many clients already" error

echo "=========================================="
echo "PostgreSQL max_connections Configuration"
echo "=========================================="
echo ""

# Get server details from docker-compose
DB_HOST=$(grep "DB_HOST=" docker-compose.yml | head -1 | cut -d'=' -f2 | tr -d ' ')

echo "Database Host: $DB_HOST"
echo ""

echo "To increase PostgreSQL max_connections, you need to:"
echo ""
echo "1. SSH into your PostgreSQL server:"
echo "   ssh user@$DB_HOST"
echo ""
echo "2. Edit PostgreSQL configuration:"
echo "   sudo nano /etc/postgresql/*/main/postgresql.conf"
echo ""
echo "3. Find and change this line:"
echo "   max_connections = 200"
echo ""
echo "4. Also check shared_buffers (should be ~25% of RAM):"
echo "   shared_buffers = 512MB"
echo ""
echo "5. Restart PostgreSQL:"
echo "   sudo systemctl restart postgresql"
echo ""
echo "6. Verify the change:"
echo "   psql -U postgres -c 'SHOW max_connections;'"
echo ""
echo "=========================================="
echo "Alternative: If you can't access PostgreSQL server,"
echo "you may need to contact your hosting provider"
echo "or database administrator to increase max_connections."
echo "=========================================="
