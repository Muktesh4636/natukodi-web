#!/bin/bash
# Quick check: why the game might be frozen.
# Run from project root: bash tools/check_game_frozen.sh
# All servers root password: Gunduata@123 (override with SERVER_PASSWORD=...)

set -e
PASSWORD="${SERVER_PASSWORD:-Gunduata@123}"
SERVERS=("72.61.254.71" "72.61.254.74" "72.62.226.41")
REMOTE_DIR="/root/apk_of_ata"

echo "=== 1. Maintenance status (if ON, game shows 'Under maintenance') ==="
curl -s --connect-timeout 5 "https://gunduata.club/api/maintenance/status/" | python3 -m json.tool 2>/dev/null || curl -s "https://gunduata.club/api/maintenance/status/"
echo ""

echo "=== 2. Current round / timer (from API) ==="
curl -s --connect-timeout 5 "https://gunduata.club/api/game/round/" | python3 -m json.tool 2>/dev/null || curl -s "https://gunduata.club/api/game/round/"
echo ""

echo "=== 3. On first backend: containers (game_timer must be Up for rounds to advance) ==="
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 root@72.61.254.71 \
  "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'dice_game|NAMES'" 2>/dev/null || echo "Could not SSH to backend."
echo ""

echo "=== 4. Turn OFF maintenance (if it was on) ==="
echo "Run on server: docker exec dice_game_web python manage.py maintenance off"
echo "Or from here (first backend):"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 \
  "cd $REMOTE_DIR && docker exec dice_game_web python manage.py maintenance off" 2>/dev/null && echo "  Maintenance turned OFF." || echo "  (Run maintenance off manually if needed.)"
echo ""

echo "=== 5. Restart game timer (if rounds are stuck) ==="
echo "Only the server that runs the game engine should have game_timer. Restart on first backend:"
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no root@72.61.254.71 "docker restart dice_game_timer 2>/dev/null" && echo "  72.61.254.71: game_timer restarted" || echo "  (Restart manually on the server that runs game_engine: docker restart dice_game_timer)"
echo ""
echo "Done. If game was frozen: maintenance is off. If timer was stuck, game_timer was restarted. Wait ~30s and refresh the app."
