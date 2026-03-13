#!/bin/bash
# Deploy backend files to all three app servers and restart web.
# Run from project root: bash tools/deploy_backend.sh
# Optional: pass file or dir paths to deploy only those (default: middleware + urls + templates)
# All servers root password: Gunduata@123 (override with SERVER_PASSWORD=...)

set -e
PASSWORD="${SERVER_PASSWORD:-Gunduata@123}"
SERVERS=(72.61.254.71 72.61.254.74 72.62.226.41)
REMOTE_DIR="/root/apk_of_ata"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default files to deploy (maintenance middleware, urls, project templates)
DEPLOY_FILES=(
  "$REPO_ROOT/backend/dice_game/maintenance_middleware.py"
  "$REPO_ROOT/backend/dice_game/urls.py"
)
DEPLOY_DIRS=(
  "$REPO_ROOT/backend/templates"
)

# If args given, use them as relative paths under backend/ or repo root
if [ $# -gt 0 ]; then
  DEPLOY_FILES=()
  DEPLOY_DIRS=()
  for arg in "$@"; do
    if [ -d "$REPO_ROOT/$arg" ]; then
      DEPLOY_DIRS+=("$REPO_ROOT/$arg")
    elif [ -f "$REPO_ROOT/$arg" ]; then
      DEPLOY_FILES+=("$REPO_ROOT/$arg")
    else
      echo "Skip (not found): $arg"
    fi
  done
fi

echo "=== Deploy to ${SERVERS[*]} ==="
for SERVER in "${SERVERS[@]}"; do
  echo "  -> $SERVER"
  for f in "${DEPLOY_FILES[@]}"; do
    [ -f "$f" ] || continue
    rel="${f#$REPO_ROOT/}"
    dir=$(dirname "$rel")
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no "$f" "root@$SERVER:$REMOTE_DIR/$dir/" 2>/dev/null || true
  done
  for d in "${DEPLOY_DIRS[@]}"; do
    [ -d "$d" ] || continue
    rel="${d#$REPO_ROOT/}"
    parent=$(dirname "$rel")
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -r "$d" "root@$SERVER:$REMOTE_DIR/$parent/" 2>/dev/null || true
  done
done

echo ""
echo "=== Restart web on all backends ==="
for SERVER in "${SERVERS[@]}"; do
  echo "  -> $SERVER"
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@$SERVER \
    "cd $REMOTE_DIR && (docker compose restart web 2>/dev/null || docker restart dice_game_web)" 2>/dev/null && echo "    OK" || echo "    fail"
done

echo ""
echo "Done. Test: https://gunduata.club/api/health/"
echo "Game settings: https://gunduata.club/api/game/settings/"
