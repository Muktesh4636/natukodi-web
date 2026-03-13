#!/bin/bash
# Deploy WebSocket-related changes: routing, load balancer nginx, restart web.
# Run from project root: bash tools/deploy_websocket.sh
# All servers root password: Gunduata@123 (override with SERVER_PASSWORD=...)
#
# Deploys:
#  - backend/game/routing.py → all 3 app servers
#  - nginx/load_balancer.conf → load balancer (187.77.186.84), then reload nginx
#  - restart web container on all 3 app servers

set -e
PASSWORD="${SERVER_PASSWORD:-Gunduata@123}"
APP_SERVERS=(72.61.254.71 72.61.254.74 72.62.226.41)
LB_SERVER="187.77.186.84"
REMOTE_DIR="/root/apk_of_ata"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== 1. Deploy routing.py to app servers ==="
for s in "${APP_SERVERS[@]}"; do
  echo "  -> $s"
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/routing.py" \
    "root@$s:$REMOTE_DIR/backend/game/" || true
done

echo ""
echo "=== 2. Deploy load_balancer.conf to LB and reload nginx ==="
sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/nginx/load_balancer.conf" \
  "root@$LB_SERVER:/tmp/load_balancer.conf" || true
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "root@$LB_SERVER" \
  "cp /tmp/load_balancer.conf /etc/nginx/sites-available/gunduata.club 2>/dev/null || cp /tmp/load_balancer.conf /etc/nginx/conf.d/load_balancer.conf 2>/dev/null || true; nginx -t && systemctl reload nginx && echo 'Nginx reloaded on LB.'" || echo "  (LB nginx reload skipped or failed)"

echo ""
echo "=== 3. Restart web on app servers ==="
for s in "${APP_SERVERS[@]}"; do
  echo "  -> $s"
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "root@$s" \
    "cd $REMOTE_DIR && (docker compose restart web 2>/dev/null || docker restart dice_game_web)" 2>/dev/null && echo "    OK" || echo "    fail"
done

echo ""
echo "Done. Test: wss://gunduata.club/ws/game/ (use scripts/test_websocket.py or a WS client)"
