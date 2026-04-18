#!/bin/bash
# Deploy ALL backend code + docker-compose + nginx to production servers.
# Run from project root: bash tools/deploy_all.sh
#
# All servers use root password: Gunduata@123
# (App: 72.61.254.71, 72.61.254.74, 72.62.226.41 | LB: 187.77.186.84)
# Override with: SERVER_PASSWORD=yourpass bash tools/deploy_all.sh

set -e
PASSWORD="${SERVER_PASSWORD:-Gunduata@123}"
APP_SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")
LB_SERVER="187.77.186.84"
REMOTE_DIR="/root/apk_of_ata"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Deploy ALL code to ${#APP_SERVERS[@]} app servers + LB ==="

for SERVER in "${APP_SERVERS[@]}"; do
  echo ""
  echo "--- $SERVER ---"

  echo "  dice_game..."
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/dice_game/urls.py" \
    "$REPO_ROOT/backend/dice_game/views.py" \
    "$REPO_ROOT/backend/dice_game/maintenance_middleware.py" \
    "$REPO_ROOT/backend/dice_game/authentication.py" \
    "$REPO_ROOT/backend/dice_game/settings.py" \
    root@$SERVER:$REMOTE_DIR/backend/dice_game/ 2>/dev/null || true

  echo "  accounts..."
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/accounts/views.py" \
    "$REPO_ROOT/backend/accounts/models.py" \
    root@$SERVER:$REMOTE_DIR/backend/accounts/ 2>/dev/null || true
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/accounts/migrations/0037_user_total_referrals_count.py" \
    root@$SERVER:$REMOTE_DIR/backend/accounts/migrations/ 2>/dev/null || true
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/accounts/management/commands/logout_all_sessions.py" \
    "$REPO_ROOT/backend/accounts/management/commands/add_referrals.py" \
    root@$SERVER:$REMOTE_DIR/backend/accounts/management/commands/ 2>/dev/null || true

  echo "  game (views, models, urls, routing, consumers, admin)..."
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/views.py" \
    "$REPO_ROOT/backend/game/models.py" \
    "$REPO_ROOT/backend/game/urls.py" \
    "$REPO_ROOT/backend/game/routing.py" \
    "$REPO_ROOT/backend/game/consumers_v2.py" \
    "$REPO_ROOT/backend/game/admin_views.py" \
    "$REPO_ROOT/backend/game/admin_utils.py" \
    "$REPO_ROOT/backend/game/admin_urls.py" \
    root@$SERVER:$REMOTE_DIR/backend/game/ 2>/dev/null || true

  echo "  game migrations + management commands..."
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/migrations/0014_whitelabel_lead.py" \
    "$REPO_ROOT/backend/game/migrations/0019_addiction_engine.py" \
    root@$SERVER:$REMOTE_DIR/backend/game/migrations/ 2>/dev/null || true
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/management/commands/daily_journey_reset.py" \
    "$REPO_ROOT/backend/game/management/commands/backfill_journeys.py" \
    root@$SERVER:$REMOTE_DIR/backend/game/management/commands/ 2>/dev/null || true

  echo "  backend root (game_engine_v3, smart_dice_engine, worker_v2)..."
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game_engine_v3.py" \
    "$REPO_ROOT/backend/smart_dice_engine.py" \
    "$REPO_ROOT/backend/worker_v2.py" \
    root@$SERVER:$REMOTE_DIR/backend/ 2>/dev/null || true

  echo "  templates (backend/templates + game/templates/admin)..."
  if [ -d "$REPO_ROOT/backend/templates" ]; then
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -r \
      "$REPO_ROOT/backend/templates/" \
      root@$SERVER:$REMOTE_DIR/backend/ 2>/dev/null || true
  fi
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/templates/admin/game_settings.html" \
    "$REPO_ROOT/backend/game/templates/admin/game_dashboard.html" \
    "$REPO_ROOT/backend/game/templates/admin/deposit_requests.html" \
    "$REPO_ROOT/backend/game/templates/admin/white_label_leads.html" \
    "$REPO_ROOT/backend/game/templates/admin/help_center.html" \
    "$REPO_ROOT/backend/game/templates/admin/user_details.html" \
    "$REPO_ROOT/backend/game/templates/admin/recent_rounds.html" \
    "$REPO_ROOT/backend/game/templates/admin/transactions.html" \
    "$REPO_ROOT/backend/game/templates/admin/create_admin.html" \
    "$REPO_ROOT/backend/game/templates/admin/edit_admin.html" \
    "$REPO_ROOT/backend/game/templates/admin/_sidebar_menu.html" \
    "$REPO_ROOT/backend/game/templates/admin/_custom_date_nav.html" \
    root@$SERVER:$REMOTE_DIR/backend/game/templates/admin/ 2>/dev/null || true

  echo "  docker-compose.yml..."
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/docker-compose.yml" \
    root@$SERVER:$REMOTE_DIR/ 2>/dev/null || true

  echo "  frontend (main site at /)..."
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER "mkdir -p /var/www/gunduata.club/frontend" 2>/dev/null || true
  sshpass -p "$PASSWORD" rsync -az -e "ssh -o StrictHostKeyChecking=no" \
    "$REPO_ROOT/frontend/" \
    root@$SERVER:/var/www/gunduata.club/frontend/ 2>/dev/null || true
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER "chown -R www-data:www-data /var/www/gunduata.club/frontend 2>/dev/null || true" 2>/dev/null || true
  echo "  nginx (gunduata.club.conf on app server)..."
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/nginx/gunduata.club.conf" \
    root@$SERVER:/tmp/gunduata.club.conf 2>/dev/null || true
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
    "cp /tmp/gunduata.club.conf /etc/nginx/sites-available/gunduata.club 2>/dev/null || cp /tmp/gunduata.club.conf /etc/nginx/conf.d/gunduata.club.conf 2>/dev/null || true; nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null; echo 'nginx done'" 2>/dev/null || true

  echo "  migrate..."
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
    "cd $REMOTE_DIR/backend && python manage.py migrate --noinput 2>/dev/null || true" 2>/dev/null || true

  # On Redis host (74), use Docker service name so containers reach local redis
  if [ "$SERVER" = "72.61.254.74" ]; then
    echo "  .env REDIS_HOST=redis (on Redis host)..."
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
      "cd $REMOTE_DIR && (grep -q '^REDIS_HOST=' .env 2>/dev/null && sed -i 's/^REDIS_HOST=.*/REDIS_HOST=redis/' .env || echo 'REDIS_HOST=redis' >> .env); echo 'done'" 2>/dev/null || true
  fi

  echo "  restart containers (web, game_timer, bet_worker, daily_reset)..."
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
    "cd $REMOTE_DIR && (docker compose up -d 2>/dev/null; docker compose restart web game_timer bet_worker daily_reset 2>/dev/null) || (docker restart dice_game_web dice_game_timer dice_game_bet_worker dice_game_daily_reset 2>/dev/null) || docker compose restart web 2>/dev/null || docker restart dice_game_web" 2>/dev/null && echo "  $SERVER: OK" || echo "  $SERVER: restart done (check logs if needed)"
done

echo ""
echo "=== Load balancer: deploy frontend + load_balancer.conf and reload nginx ==="
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "mkdir -p /var/www/gunduata.club/frontend" 2>/dev/null || true
sshpass -p "$PASSWORD" rsync -az -e "ssh -o StrictHostKeyChecking=no" \
  "$REPO_ROOT/frontend/" \
  root@$LB_SERVER:/var/www/gunduata.club/frontend/ 2>/dev/null || true
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER "chown -R www-data:www-data /var/www/gunduata.club/frontend 2>/dev/null; chmod 755 /var/www/gunduata.club /var/www/gunduata.club/frontend 2>/dev/null" 2>/dev/null || true
sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/nginx/load_balancer.conf" \
  "root@$LB_SERVER:/tmp/load_balancer.conf" 2>/dev/null || true
# LB uses conf.d/gunduata.club.conf (not sites-available); update the file that is actually loaded
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$LB_SERVER \
  "cp /tmp/load_balancer.conf /etc/nginx/conf.d/gunduata.club.conf 2>/dev/null || true; cp /tmp/load_balancer.conf /etc/nginx/sites-available/gunduata.club 2>/dev/null || true; nginx -t && systemctl reload nginx && echo 'LB nginx reloaded.'" 2>/dev/null || echo "  (LB nginx skipped or failed)"

echo ""
echo "=== Health check ==="
for SERVER in "${APP_SERVERS[@]}"; do
  CODE=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:8001/api/health/ 2>/dev/null" || echo "000")
  if [ "$CODE" = "200" ]; then
    echo "  $SERVER: OK (200)"
  else
    echo "  $SERVER: HTTP $CODE"
  fi
done

echo ""
echo "Done. Test: https://gunduata.club/api/health/"
