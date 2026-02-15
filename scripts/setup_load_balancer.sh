#!/bin/bash

# Setup Nginx Load Balancer
# This can run on Server 1, Server 2, or a separate server

set -e

echo "🔧 Setting up Nginx Load Balancer..."

# Determine which server to install on (default: Server 1)
LB_SERVER="${1:-72.61.254.71}"
PASSWORD="Gunduata@123"

echo "Installing load balancer on: $LB_SERVER"

sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER << 'LB_SETUP'
# Install Nginx if not installed
if ! command -v nginx &> /dev/null; then
    apt-get update -qq
    apt-get install -y nginx > /dev/null 2>&1
fi

# Backup existing config
if [ -f /etc/nginx/sites-available/default ]; then
    cp /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup.$(date +%s)
fi

# Create load balancer config
cat > /etc/nginx/sites-available/load_balancer << 'EOF'
# Nginx Load Balancer Configuration

upstream backend_servers {
    least_conn;
    server 72.61.254.71:8001 max_fails=3 fail_timeout=30s;
    server 72.61.254.74:8001 max_fails=3 fail_timeout=30s;
}

map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;
    server_name gunduata.online www.gunduata.online _;

    proxy_connect_timeout 7d;
    proxy_send_timeout 7d;
    proxy_read_timeout 7d;

    # WebSocket support
    location /ws/ {
        proxy_pass http://backend_servers;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }

    # API and static files
    location / {
        proxy_pass http://backend_servers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF

# Enable the site
ln -sf /etc/nginx/sites-available/load_balancer /etc/nginx/sites-enabled/load_balancer
rm -f /etc/nginx/sites-enabled/default

# Test configuration
nginx -t

# Restart Nginx
systemctl restart nginx
systemctl enable nginx

sleep 2

# Check status
if systemctl is-active --quiet nginx; then
    echo "✅ Nginx Load Balancer started successfully"
    echo ""
    echo "Backend servers configured:"
    echo "  - Server 1: 72.61.254.71:8001"
    echo "  - Server 2: 72.61.254.74:8001"
    echo ""
    echo "Load balancing method: least_conn (distributes to server with fewest connections)"
else
    echo "❌ Nginx failed to start"
    systemctl status nginx --no-pager | tail -10
fi
LB_SETUP

echo ""
echo "✅ Load balancer setup complete!"
