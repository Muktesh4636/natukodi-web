# SSL/HTTPS Setup Guide for gunduata.online

This guide will help you set up SSL certificates using Let's Encrypt for your domain.

## Prerequisites

1. ✅ Domain `gunduata.online` DNS A record pointing to `72.61.254.71`
2. ✅ Domain `www.gunduata.online` DNS A record pointing to `72.61.254.71`
3. ✅ Nginx installed and configured
4. ✅ Port 80 and 443 open in firewall

## Quick Setup

### Step 1: Copy updated Nginx config to server

From your local machine:
```bash
scp nginx/gunduata.online.conf root@72.61.254.71:/tmp/
```

### Step 2: SSH into your server

```bash
ssh root@72.61.254.71
```

### Step 3: Update Nginx configuration

```bash
# Backup existing config (if any)
cp /etc/nginx/sites-available/gunduata.online.conf /etc/nginx/sites-available/gunduata.online.conf.backup

# Copy new config
cp /tmp/gunduata.online.conf /etc/nginx/sites-available/gunduata.online.conf

# Test configuration
nginx -t

# If test passes, restart Nginx
systemctl restart nginx
```

### Step 4: Install Certbot

```bash
apt update
apt install -y certbot python3-certbot-nginx
```

### Step 5: Obtain SSL Certificate

```bash
certbot --nginx -d gunduata.online -d www.gunduata.online
```

Follow the prompts:
- Enter your email address (for renewal notifications)
- Agree to terms of service
- Choose whether to redirect HTTP to HTTPS (recommended: Yes)

### Step 6: Verify SSL is working

Visit:
- https://gunduata.online
- https://www.gunduata.online

Both should show a secure connection (padlock icon).

### Step 7: Set up auto-renewal

Certbot automatically sets up a systemd timer for renewal. Verify it's active:

```bash
systemctl status certbot.timer
```

Test renewal (dry run):
```bash
certbot renew --dry-run
```

---

## Manual Setup (Alternative)

If the automated setup doesn't work, you can manually obtain the certificate:

```bash
# Stop Nginx temporarily
systemctl stop nginx

# Obtain certificate using standalone mode
certbot certonly --standalone -d gunduata.online -d www.gunduata.online

# Start Nginx
systemctl start nginx
```

Then manually update the Nginx config with the certificate paths.

---

## Troubleshooting

### Certificate not obtained

**Check DNS:**
```bash
dig gunduata.online +short
# Should return: 72.61.254.71
```

**Check port 80 is accessible:**
```bash
# From another machine
curl -I http://gunduata.online
```

**Check Nginx logs:**
```bash
tail -f /var/log/nginx/error.log
```

**Check Certbot logs:**
```bash
tail -f /var/log/letsencrypt/letsencrypt.log
```

### Certificate renewal failing

**Test renewal manually:**
```bash
certbot renew --dry-run
```

**Check renewal timer:**
```bash
systemctl status certbot.timer
systemctl list-timers | grep certbot
```

**Manually renew:**
```bash
certbot renew
systemctl reload nginx
```

### SSL errors in browser

**Check certificate:**
```bash
openssl s_client -connect gunduata.online:443 -servername gunduata.online
```

**Verify certificate files exist:**
```bash
ls -la /etc/letsencrypt/live/gunduata.online/
```

**Check Nginx config:**
```bash
nginx -t
```

---

## Security Notes

- ✅ SSL certificates auto-renew every 90 days
- ✅ HTTP automatically redirects to HTTPS
- ✅ Modern TLS protocols (1.2 and 1.3) enabled
- ✅ Security headers configured
- ✅ HSTS (HTTP Strict Transport Security) enabled

---

## Certificate Files Location

- Certificate: `/etc/letsencrypt/live/gunduata.online/fullchain.pem`
- Private Key: `/etc/letsencrypt/live/gunduata.online/privkey.pem`
- Certificate Chain: `/etc/letsencrypt/live/gunduata.online/chain.pem`

**⚠️ Never share or expose your private key file!**

---

## After SSL Setup

1. Update your Android app's API base URL to use `https://gunduata.online`
2. Update Django `CSRF_TRUSTED_ORIGINS` to include `https://gunduata.online` (already done)
3. Update `.env` file `ALLOWED_HOSTS` to include `gunduata.online` (already done)
