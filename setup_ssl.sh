#!/bin/bash

# Script to set up SSL certificate for gunduata.club
# Run this on your server: 72.61.254.71

SERVER_USER="root"
SERVER_IP="72.61.254.71"
DOMAIN="gunduata.club"
WWW_DOMAIN="www.gunduata.club"

echo "=== Setting up SSL Certificate for $DOMAIN ==="
echo ""

# Check if running on the server
if [ "$(hostname -I | grep -o '72.61.254.71')" != "72.61.254.71" ]; then
    echo "This script should be run on the server (72.61.254.71)"
    echo ""
    echo "SSH into your server and run:"
    echo "  ssh $SERVER_USER@$SERVER_IP"
    echo "  bash <(curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot-nginx.sh)"
    echo ""
    echo "Or follow the manual steps below:"
    exit 0
fi

# Check if Nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "❌ Nginx is not installed. Please install Nginx first."
    echo "Run: apt update && apt install -y nginx"
    exit 1
fi

# Check if Nginx is running
if ! systemctl is-active --quiet nginx; then
    echo "⚠️  Nginx is not running. Starting Nginx..."
    systemctl start nginx
    systemctl enable nginx
fi

# Install Certbot if not already installed
if ! command -v certbot &> /dev/null; then
    echo "Installing Certbot..."
    apt update
    apt install -y certbot python3-certbot-nginx
fi

# Create directory for Let's Encrypt challenges
mkdir -p /var/www/certbot

# Make sure port 80 is open
echo "Checking firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 80/tcp
    ufw allow 443/tcp
fi

# Verify DNS is pointing to this server
echo ""
echo "⚠️  IMPORTANT: Make sure your domain DNS is configured:"
echo "   $DOMAIN should have an A record pointing to $(hostname -I | awk '{print $1}')"
echo "   $WWW_DOMAIN should have an A record pointing to $(hostname -I | awk '{print $1}')"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

# Obtain SSL certificate
echo ""
echo "Obtaining SSL certificate from Let's Encrypt..."
certbot --nginx -d $DOMAIN -d $WWW_DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN --redirect

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SSL certificate obtained successfully!"
    echo ""
    echo "Your site is now available at:"
    echo "  https://$DOMAIN"
    echo "  https://$WWW_DOMAIN"
    echo ""
    echo "HTTP traffic will automatically redirect to HTTPS."
    echo ""
    echo "Certificate will auto-renew. Test renewal with:"
    echo "  certbot renew --dry-run"
else
    echo ""
    echo "❌ Failed to obtain SSL certificate."
    echo "Common issues:"
    echo "  1. DNS not pointing to this server"
    echo "  2. Port 80 not accessible from internet"
    echo "  3. Domain already has a certificate"
    echo ""
    echo "Check logs: /var/log/letsencrypt/letsencrypt.log"
    exit 1
fi

# Set up auto-renewal
echo ""
echo "Setting up automatic certificate renewal..."
systemctl enable certbot.timer
systemctl start certbot.timer

echo ""
echo "✅ SSL setup complete!"
echo ""
echo "To verify SSL renewal is scheduled:"
echo "  systemctl status certbot.timer"
