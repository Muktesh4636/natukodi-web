#!/bin/bash

# Deploy LOCAL code (from your Mac) to all three servers.
# Use this when franchise and other local changes are not yet on GitHub.
# Servers will get exactly what you have locally.

set -e

PASSWORD="Gunduata@123"
# Optional: if 72.62.226.41 has a different root password, set it:
# export SERVER_3_PASSWORD="other_password"
SERVER_3_PASSWORD="${SERVER_3_PASSWORD:-$PASSWORD}"
SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")
REMOTE_DIR="/root/apk_of_ata"

get_password() {
    if [ "$1" == "72.62.226.41" ]; then
        echo "$SERVER_3_PASSWORD"
    else
        echo "$PASSWORD"
    fi
}

echo "🚀 Deploying LOCAL code to all ${#SERVERS[@]} servers..."
echo "   (Franchise model and all local changes will be deployed)"
echo ""

if [ ! -f "docker-compose.yml" ] || [ ! -d "backend" ]; then
    echo "❌ Error: Run this script from the project root (where docker-compose.yml and backend/ exist)."
    exit 1
fi

# Check that templates exist locally (ensures you're in the right repo with latest changes)
if [ ! -f "backend/game/templates/admin/franchise_admin_details.html" ]; then
    echo "❌ Error: backend/game/templates/admin/franchise_admin_details.html not found. Run from project root."
    exit 1
fi
echo "   ✓ Local backend and templates found"

# 1. Copy files to each server
for SERVER in "${SERVERS[@]}"; do
    PW=$(get_password "$SERVER")
    echo "--------------------------------------------------"
    echo "📤 Uploading to $SERVER ..."
    if ! sshpass -p "$PW" scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 docker-compose.yml root@${SERVER}:${REMOTE_DIR}/ 2>/dev/null; then
        echo "   ⚠️  Skip $SERVER (SSH failed: check password or use SERVER_3_PASSWORD=... for 72.62.226.41)"
        continue
    fi
    if ! sshpass -p "$PW" rsync -avz --progress \
        -e "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='venv' \
        --exclude='env' \
        --exclude='db.sqlite3' \
        --exclude='*.log' \
        --exclude='logs' \
        --exclude='staticfiles' \
        --exclude='media' \
        backend/ root@${SERVER}:${REMOTE_DIR}/backend/ 2>/dev/null; then
        echo "   ⚠️  Skip $SERVER (rsync failed)"
        continue
    fi
    echo "   ✓ Files copied to $SERVER"
done

# 1b. Verify templates reached the first server (so updates are not missed)
echo "--------------------------------------------------"
echo "🔍 Verifying deployment..."
FIRST_SERVER="${SERVERS[0]}"
PW=$(get_password "$FIRST_SERVER")
if sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$FIRST_SERVER "grep -q 'Assign player to this franchise' ${REMOTE_DIR}/backend/game/templates/admin/franchise_admin_details.html 2>/dev/null"; then
    echo "   ✓ Templates on $FIRST_SERVER contain expected updates"
else
    echo "   ⚠️  WARNING: Template on $FIRST_SERVER may be old or path wrong. Check REMOTE_DIR=${REMOTE_DIR}"
fi

# 2. On each server: fix Redis on Server 3, then restart Docker
for SERVER in "${SERVERS[@]}"; do
    PW=$(get_password "$SERVER")
    echo "--------------------------------------------------"
    echo "🔄 Restarting Docker on $SERVER ..."
    if ! sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$SERVER "cd $REMOTE_DIR && \
        if [ \"$SERVER\" == \"72.62.226.41\" ]; then systemctl stop redis-server 2>/dev/null || true; systemctl disable redis-server 2>/dev/null || true; fi && \
        docker compose down --remove-orphans && \
        docker builder prune -f 2>/dev/null || true && \
        docker compose up -d --build && \
        echo \"   ✅ $SERVER done\"" 2>/dev/null; then
        echo "   ⚠️  Skip restart on $SERVER (SSH failed)"
    fi
done

# 3. Run migrations (DB is shared; run on first server where web is up)
echo "--------------------------------------------------"
echo "📦 Running migrations..."
for SERVER in 72.61.254.71 72.61.254.74 72.62.226.41; do
    PW=$(get_password "$SERVER")
    if sshpass -p "$PW" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@$SERVER "cd $REMOTE_DIR && docker compose exec -T web python manage.py migrate --noinput" 2>/dev/null; then
        echo "   Migrations completed on $SERVER"
        break
    fi
done

echo ""
echo "🎉 Local deployment complete! Franchise model and all local code are now on all three servers."
echo "   Check admin: http://72.61.254.71:8001/game-admin/ (or your domain)"
echo ""
echo "   If you don't see updates in the browser:"
echo "   • Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)"
echo "   • Or open the site in an incognito/private window"
echo "   • If using a domain (e.g. gunduata.club), ensure it points to a server that was updated"
echo ""
echo "Monitoring logs on 72.61.254.71 for 10 seconds..."
sleep 10
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 "docker logs --tail 30 dice_game_web"
