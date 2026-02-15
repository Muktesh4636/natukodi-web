#!/bin/bash

# Script to optimize PostgreSQL for high load (4 CPU / 16GB RAM server)
# This increases max_connections and optimizes memory settings

set -e

# Configuration
SERVER_USER="root"
SERVER_IP="72.61.255.231"
SERVER_PASS="Gunduata@123"

echo "=========================================="
echo "PostgreSQL Optimization for High Load"
echo "=========================================="
echo ""

echo "Connecting to PostgreSQL server: $SERVER_IP"
echo ""

# Find PostgreSQL config file
CONFIG_FILE=$(sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "sudo find /etc -name 'postgresql.conf' 2>/dev/null | head -1")

if [ -z "$CONFIG_FILE" ]; then
    echo "ERROR: Could not find PostgreSQL config file"
    exit 1
fi

echo "Found config file: $CONFIG_FILE"
echo ""

# Backup and update config
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << ENDSSH
    # Backup config file
    sudo cp "$CONFIG_FILE" "${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backup created"
    
    # Update max_connections to 500 (for 4 CPU / 16GB RAM server)
    sudo sed -i 's/^max_connections = .*/max_connections = 500/' "$CONFIG_FILE"
    echo "Updated max_connections to 500"
    
    # Optimize shared_buffers (25% of RAM = 4GB for 16GB server)
    sudo sed -i 's/^shared_buffers = .*/shared_buffers = 4GB/' "$CONFIG_FILE" || echo "shared_buffers = 4GB" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "Updated shared_buffers to 4GB"
    
    # Optimize effective_cache_size (75% of RAM = 12GB)
    sudo sed -i 's/^effective_cache_size = .*/effective_cache_size = 12GB/' "$CONFIG_FILE" || echo "effective_cache_size = 12GB" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "Updated effective_cache_size to 12GB"
    
    # Optimize maintenance_work_mem (1GB for 16GB server)
    sudo sed -i 's/^maintenance_work_mem = .*/maintenance_work_mem = 1GB/' "$CONFIG_FILE" || echo "maintenance_work_mem = 1GB" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "Updated maintenance_work_mem to 1GB"
    
    # Optimize work_mem (for 500 connections: 16GB / 500 = ~32MB per connection)
    sudo sed -i 's/^work_mem = .*/work_mem = 32MB/' "$CONFIG_FILE" || echo "work_mem = 32MB" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "Updated work_mem to 32MB"
    
    echo ""
    echo "Configuration updated successfully!"
ENDSSH

# Restart PostgreSQL
echo ""
echo "Restarting PostgreSQL..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" "sudo systemctl restart postgresql && echo 'PostgreSQL restarted successfully' || echo 'Restart failed'"

# Verify the changes
echo ""
echo "Verifying changes..."
sleep 3
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << ENDSSH
    echo "Current PostgreSQL settings:"
    sudo -u postgres psql -c "SHOW max_connections;"
    sudo -u postgres psql -c "SHOW shared_buffers;"
    sudo -u postgres psql -c "SHOW effective_cache_size;"
ENDSSH

echo ""
echo "=========================================="
echo "PostgreSQL optimization complete!"
echo "=========================================="
