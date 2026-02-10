# Nginx Reverse Proxy Setup for gunduata.online

This guide will help you set up Nginx to route `gunduata.online` to your Django application running on port 8001.

## Quick Setup

### Step 1: Copy Nginx config to server

From your local machine:
```bash
scp nginx/gunduata.online.conf root@72.61.254.71:/tmp/
```

### Step 2: SSH into your server and set up Nginx

```bash
ssh root@72.61.254.71
```

### Step 3: Install and configure Nginx

```bash
# Install Nginx
apt update
apt install -y nginx

# Copy the configuration file
cp /tmp/gunduata.online.conf /etc/nginx/sites-available/gunduata.online.conf

# Enable the site
ln -sf /etc/nginx/sites-available/gunduata.online.conf /etc/nginx/sites-enabled/

# Remove default site (optional)
rm /etc/nginx/sites-enabled/default

# Test configuration
nginx -t

# Restart Nginx
systemctl restart nginx
systemctl enable nginx
```

### Step 4: Verify DNS is pointing to your server

Make sure your domain `gunduata.online` has an A record pointing to `72.61.254.71`:

```bash
# Check DNS
dig gunduata.online +short
# Should return: 72.61.254.71
```

### Step 5: Test the setup

Visit:
- http://gunduata.online
- http://www.gunduata.online

Both should now show your Django application.

---

## Setting up SSL (HTTPS) - Optional but Recommended

### Step 1: Install Certbot

```bash
apt install -y certbot python3-certbot-nginx
```

### Step 2: Obtain SSL certificate

```bash
certbot --nginx -d gunduata.online -d www.gunduata.online
```

Follow the prompts. Certbot will:
- Automatically configure SSL
- Set up automatic renewal
- Redirect HTTP to HTTPS

### Step 3: Verify SSL renewal

```bash
certbot renew --dry-run
```

---

## Troubleshooting

### Check Nginx status
```bash
systemctl status nginx
```

### Check Nginx logs
```bash
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

### Test Nginx configuration
```bash
nginx -t
```

### Restart Nginx
```bash
systemctl restart nginx
```

### Check if port 80 is open
```bash
ufw status
# If needed:
ufw allow 80/tcp
ufw allow 443/tcp
```

### Verify Django app is running
```bash
curl http://localhost:8001/
```

---

## Notes

- Your Django app runs on port **8001** (mapped from container port 8080)
- Nginx listens on port **80** (HTTP) and **443** (HTTPS after SSL setup)
- Make sure your `.env` file includes `gunduata.online` in `ALLOWED_HOSTS`
- The Django `CSRF_TRUSTED_ORIGINS` already includes `gunduata.online` domains
