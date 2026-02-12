#!/bin/bash

# Automated script to increase PostgreSQL max_connections
# Usage: ./scripts/increase_postgres_max_connections_auto.sh

set -e

# Configuration
SERVER_USER="root"
SERVER_IP="72.61.254.74"
SERVER_PASS="Gunduata@123"

echo "=========================================="
echo "PostgreSQL max_connections Configuration"
echo "=========================================="
echo ""

echo "Connecting to PostgreSQL server: $SERVER_IP"
echo ""

# First, check current max_connections
echo "Step 1: Checking current max_connections..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
    echo "Current PostgreSQL max_connections:"
    sudo -u postgres psql -c "SHOW max_connections;" 2>/dev/null || echo "Could not check. PostgreSQL may not be installed locally."
    echo ""
ENDSSH

# Find PostgreSQL config file
echo "Step 2: Finding PostgreSQL configuration file..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
    # Try to find postgresql.conf
    CONFIG_FILE=$(sudo find /etc -name "postgresql.conf" 2>/dev/null | head -1)
    
    if [ -z "$CONFIG_FILE" ]; then
        echo "PostgreSQL config file not found in /etc"
        echo "Checking if PostgreSQL is installed..."
        which psql || echo "PostgreSQL client not found"
        echo ""
        echo "If PostgreSQL is on a remote server, you may need to:"
        echo "1. SSH into the PostgreSQL server directly"
        echo "2. Or configure PostgreSQL to allow remote connections"
        exit 1
    fi
    
    echo "Found config file: $CONFIG_FILE"
    echo ""
    
    # Check current max_connections value
    CURRENT_MAX=$(sudo grep "^max_connections" "$CONFIG_FILE" | head -1 | awk '{print $3}' | tr -d '#')
    echo "Current max_connections setting: $CURRENT_MAX"
    echo ""
ENDSSH

# Backup and update config
echo "Step 3: Backing up and updating PostgreSQL configuration..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
    CONFIG_FILE=$(sudo find /etc -name "postgresql.conf" 2>/dev/null | head -1)
    
    if [ -z "$CONFIG_FILE" ]; then
        echo "ERROR: Could not find PostgreSQL config file"
        exit 1
    fi
    
    # Backup config file
    sudo cp "$CONFIG_FILE" "${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backup created: ${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Update max_connections
    # First, comment out existing line if present
    sudo sed -i 's/^max_connections/#max_connections/' "$CONFIG_FILE"
    
    # Add new max_connections setting
    echo "" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "# Increased max_connections for load testing - $(date)" | sudo tee -a "$CONFIG_FILE" > /dev/null
    echo "max_connections = 200" | sudo tee -a "$CONFIG_FILE" > /dev/null
    
    echo "Updated max_connections to 200"
    echo ""
ENDSSH

# Restart PostgreSQL
echo "Step 4: Restarting PostgreSQL..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
    echo "Restarting PostgreSQL service..."
    sudo systemctl restart postgresql || sudo service postgresql restart || {
        echo "WARNING: Could not restart PostgreSQL automatically"
        echo "Please restart PostgreSQL manually:"
        echo "  sudo systemctl restart postgresql"
        echo "  OR"
        echo "  sudo service postgresql restart"
    }
    echo ""
ENDSSH

# Verify the change
echo "Step 5: Verifying the change..."
sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
    sleep 2
    echo "New PostgreSQL max_connections:"
    sudo -u postgres psql -c "SHOW max_connections;" 2>/dev/null || echo "Could not verify. Please check manually."
    echo ""
ENDSSH

echo "=========================================="
echo "Configuration update complete!"
echo "=========================================="
echo ""
echo "If PostgreSQL is running on a different server,"
echo "you may need to update the config on that server instead."
echo ""
