#!/usr/bin/env bash
# Run Locust load test and open the web UI.
# Usage:
#   ./scripts/run_locust.sh                    # default host https://gunduata.online
#   ./scripts/run_locust.sh http://localhost:8000

set -e
HOST="${1:-https://gunduata.online}"

# Install locust if missing
if ! python3 -c "import locust" 2>/dev/null; then
    echo "Installing locust..."
    pip install locust
fi

echo "Starting Locust with host=$HOST"
echo "Open the Locust web UI at: http://localhost:8089"
echo "If you're on a remote server, use: http://YOUR_SERVER_IP:8089"
echo ""

# Bind to 0.0.0.0 so you can access from another machine (e.g. browser on your laptop)
exec locust -f locustfile.py --host="$HOST" --web-host=0.0.0.0 --web-port=8089
