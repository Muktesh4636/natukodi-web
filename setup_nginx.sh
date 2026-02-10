#!/bin/bash

# Script to set up Nginx reverse proxy for gunduata.online
# Run this on your server: 72.61.254.71

SERVER_USER="root"
SERVER_IP="72.61.254.71"
NGINX_CONF_PATH="/etc/nginx/sites-available/gunduata.online.conf"
NGINX_ENABLED_PATH="/etc/nginx/sites-enabled/gunduata.online.conf"

echo "=== Setting up Nginx Reverse Proxy ==="
echo ""

# Check if running on the server
if [ "$(hostname -I | grep -o '72.61.254.71')" != "72.61.254.71" ]; then
    echo "This script should be run on the server (72.61.254.71)"
    echo "Copying nginx config to server..."
    
    # Copy nginx config to server
    scp nginx/gunduata.online.conf $SERVER_USER@$SERVER_IP:/tmp/gunduata.online.conf
    
    echo ""
    echo "Now SSH into your server and run:"
    echo "  ssh $SERVER_USER@$SERVER_IP"
    echo "  sudo bash /tmp/gunduata.online.conf"
    echo ""
    echo "Or run these commands manually on the server:"
    echo "  sudo apt update && sudo apt install -y nginx"
    echo "  sudo cp /tmp/gunduata.online.conf $NGINX_CONF_PATH"
    echo "  sudo ln -sf $NGINX_CONF_PATH $NGINX_ENABLED_PATH"
    echo "  sudo nginx -t"
    echo "  sudo systemctl restart nginx"
    exit 0
fi

# Install Nginx if not already installed
if ! command -v nginx &> /dev/null; then
    echo "Installing Nginx..."
    apt update
    apt install -y nginx
fi

# Copy nginx configuration
echo "Setting up Nginx configuration..."
if [ -f "/tmp/gunduata.online.conf" ]; then
    cp /tmp/gunduata.online.conf $NGINX_CONF_PATH
else
    echo "Error: Nginx config file not found at /tmp/gunduata.online.conf"
    echo "Please copy nginx/gunduata.online.conf to the server first"
    exit 1
fi

# Create symlink to enable the site
ln -sf $NGINX_CONF_PATH $NGINX_ENABLED_PATH

# Remove default Nginx site if it exists
if [ -f "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
fi

# Test Nginx configuration
echo "Testing Nginx configuration..."
nginx -t

if [ $? -ne 0 ]; then
    echo "❌ Nginx configuration test failed. Please check the config file."
    exit 1
fi

# Restart Nginx
echo "Restarting Nginx..."
systemctl restart nginx
systemctl enable nginx

echo ""
echo "✅ Nginx reverse proxy configured successfully!"
echo ""
echo "Your site should now be accessible at:"
echo "  http://gunduata.online"
echo "  http://www.gunduata.online"
echo ""
echo "To set up SSL (HTTPS), run:"
echo "  sudo apt install -y certbot python3-certbot-nginx"
echo "  sudo certbot --nginx -d gunduata.online -d www.gunduata.online"
echo ""
echo "After SSL setup, uncomment the HTTPS server block in:"
echo "  $NGINX_CONF_PATH"
