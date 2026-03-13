#!/bin/bash
# Deploy leaderboard route and view to all production servers.
# Fixes 404 on /api/auth/leaderboard/ (gunduata.club or gunduata.online).
# All servers root password: Gunduata@123 (override with SERVER_PASSWORD=...)
set -e
PASSWORD="${SERVER_PASSWORD:-Gunduata@123}"
SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")
REMOTE_DIR="/root/apk_of_ata"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Deploying backend (urls, views, auth, maintenance, admin, logout-all) to ${#SERVERS[@]} servers..."
for SERVER in "${SERVERS[@]}"; do
  echo "  -> $SERVER"
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/dice_game/urls.py" \
    "$REPO_ROOT/backend/dice_game/views.py" \
    "$REPO_ROOT/backend/dice_game/maintenance_middleware.py" \
    "$REPO_ROOT/backend/dice_game/authentication.py" \
    "$REPO_ROOT/backend/dice_game/settings.py" \
    root@$SERVER:$REMOTE_DIR/backend/dice_game/
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/accounts/views.py" \
    "$REPO_ROOT/backend/accounts/models.py" \
    root@$SERVER:$REMOTE_DIR/backend/accounts/
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/accounts/migrations/0037_user_total_referrals_count.py" \
    root@$SERVER:$REMOTE_DIR/backend/accounts/migrations/ 2>/dev/null || true
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/accounts/management/commands/logout_all_sessions.py" \
    "$REPO_ROOT/backend/accounts/management/commands/add_referrals.py" \
    root@$SERVER:$REMOTE_DIR/backend/accounts/management/commands/
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/admin_views.py" \
    "$REPO_ROOT/backend/game/admin_utils.py" \
    "$REPO_ROOT/backend/game/admin_urls.py" \
    "$REPO_ROOT/backend/game/views.py" \
    "$REPO_ROOT/backend/game/models.py" \
    root@$SERVER:$REMOTE_DIR/backend/game/
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/templates/admin/game_settings.html" \
    "$REPO_ROOT/backend/game/templates/admin/game_dashboard.html" \
    "$REPO_ROOT/backend/game/templates/admin/dice_control.html" \
    "$REPO_ROOT/backend/game/templates/admin/deposit_requests.html" \
    "$REPO_ROOT/backend/game/templates/admin/dice_controlled_rounds.html" \
    "$REPO_ROOT/backend/game/templates/admin/white_label_leads.html" \
    "$REPO_ROOT/backend/game/templates/admin/help_center.html" \
    "$REPO_ROOT/backend/game/templates/admin/user_details.html" \
    "$REPO_ROOT/backend/game/templates/admin/recent_rounds.html" \
    "$REPO_ROOT/backend/game/templates/admin/create_admin.html" \
    "$REPO_ROOT/backend/game/templates/admin/edit_admin.html" \
    "$REPO_ROOT/backend/game/templates/admin/_sidebar_menu.html" \
    root@$SERVER:$REMOTE_DIR/backend/game/templates/admin/
  if [ -d "$REPO_ROOT/backend/templates" ]; then
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -r \
      "$REPO_ROOT/backend/templates/" \
      root@$SERVER:$REMOTE_DIR/backend/
  fi
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no \
    "$REPO_ROOT/backend/game/migrations/0014_whitelabel_lead.py" \
    root@$SERVER:$REMOTE_DIR/backend/game/migrations/ 2>/dev/null || true
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
    "cd $REMOTE_DIR/backend && python manage.py migrate accounts --noinput 2>/dev/null || true"
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
    "cd $REMOTE_DIR && (docker compose restart web 2>/dev/null || docker restart dice_game_web)"
  echo "  $SERVER: restarted"
done
echo ""
echo "Done. Verifying health on each server (curl from server localhost)..."
for SERVER in "${SERVERS[@]}"; do
  CODE=$(sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:8001/api/health/ 2>/dev/null" || echo "000")
  if [ "$CODE" = "200" ]; then
    echo "  $SERVER: OK (200)"
  else
    echo "  $SERVER: got $CODE (check: ssh root@$SERVER 'cd $REMOTE_DIR && docker compose logs web --tail 50')"
  fi
done
echo ""
echo "Test from browser: https://gunduata.club/api/health/"
