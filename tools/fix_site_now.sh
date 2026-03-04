#!/bin/bash
# Get gunduata.club working: deploy code, check app + nginx on the server.
# Run from project root: bash tools/fix_site_now.sh

set -e
PASSWORD="${SERVER_PASSWORD:-Gunduata@123}"
# Server that serves gunduata.club (from setup_nginx.sh)
SERVER="72.61.254.71"
REMOTE_DIR="/root/apk_of_ata"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== 1. Deploy latest backend (login + leaderboard fixes) to $SERVER ==="
sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/backend/accounts/views.py" \
  root@$SERVER:$REMOTE_DIR/backend/accounts/views.py
sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/backend/dice_game/urls.py" \
  root@$SERVER:$REMOTE_DIR/backend/dice_game/urls.py
echo "  Restarting web container..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
  "cd $REMOTE_DIR && (docker compose restart web 2>/dev/null || docker restart dice_game_web)"
echo ""

echo "=== 2. Copy Nginx config (longer timeouts) and reload ==="
sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/nginx/gunduata.club.conf" \
  root@$SERVER:/tmp/gunduata.club.conf
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
  "cp /tmp/gunduata.club.conf /etc/nginx/sites-available/gunduata.club.conf 2>/dev/null || true; nginx -t && systemctl reload nginx && echo 'Nginx reloaded.'"
echo ""

echo "=== 3. Quick health check on server ==="
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
  "echo 'Docker:' && docker ps --format '{{.Names}} {{.Status}}' | head -5; echo ''; echo 'Port 8001:' && (ss -tlnp | grep 8001 || netstat -tlnp 2>/dev/null | grep 8001 || echo 'Nothing on 8001'); echo ''; curl -s -o /dev/null -w 'Local API: HTTP %{http_code}\n' --connect-timeout 5 http://127.0.0.1:8001/api/loading-time/ 2>/dev/null || echo 'Could not reach app on 8001'"

echo ""
echo "=== Done. Test in browser: https://gunduata.club ==="
echo "If still 504: In Cloudflare DNS, ensure gunduata.club A record points to $SERVER (with orange cloud)."
