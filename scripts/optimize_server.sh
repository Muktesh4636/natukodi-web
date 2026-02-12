#!/bin/bash

# Server Optimization Script
# This script helps optimize your server configuration before scaling

echo "=========================================="
echo "Server Optimization Checklist"
echo "=========================================="
echo ""

# Check 1: PostgreSQL max_connections
echo "1. Checking PostgreSQL max_connections..."
echo "   Run this SQL query on your PostgreSQL server:"
echo "   SELECT name, setting FROM pg_settings WHERE name = 'max_connections';"
echo ""
echo "   If max_connections < 200, increase it:"
echo "   sudo nano /etc/postgresql/*/main/postgresql.conf"
echo "   # Change: max_connections = 200"
echo "   sudo systemctl restart postgresql"
echo ""

# Check 2: Current active connections
echo "2. Check current database connections:"
echo "   Run: SELECT count(*) FROM pg_stat_activity;"
echo "   If this is close to max_connections, you need to increase it."
echo ""

# Check 3: Server resources
echo "3. Check server resources:"
echo "   CPU: top (or htop)"
echo "   Memory: free -h"
echo "   Docker stats: docker stats"
echo ""

# Check 4: Current server setup
echo "4. Current server configuration:"
echo "   - Using Daphne (single-process) - Consider switching to Gunicorn"
echo "   - CPU Limit: 1.5 cores"
echo "   - Memory Limit: 2GB"
echo ""

echo "=========================================="
echo "Recommended Actions (in order):"
echo "=========================================="
echo ""
echo "✅ PRIORITY 1: Fix Database Connections"
echo "   - Increase PostgreSQL max_connections to 200-300"
echo "   - This will fix 'too many clients' errors"
echo ""
echo "✅ PRIORITY 2: Deploy Missing Routes"
echo "   - Run: ./deploy_auto.sh"
echo "   - This will fix 401 authentication errors"
echo ""
echo "✅ PRIORITY 3: Switch to Gunicorn (Optional but Recommended)"
echo "   - Better CPU utilization"
echo "   - Can handle more concurrent requests"
echo ""
echo "✅ PRIORITY 4: Test Again"
echo "   - Run load test with optimizations"
echo "   - Monitor: docker stats, database connections"
echo ""
echo "=========================================="
echo "After optimization, you should be able to"
echo "handle 100-200 concurrent users without"
echo "increasing server resources."
echo "=========================================="
