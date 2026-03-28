#!/usr/bin/env bash
# Run Locust load test and open the web UI.
# Usage:
#   ./scripts/run_locust.sh                              # local API (Docker): 127.0.0.1:8001
#   ./scripts/run_locust.sh https://gunduata.club        # production
#   ./scripts/run_locust.sh http://127.0.0.1:8000         # manage.py default port

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1
if [[ ! -f "$REPO_ROOT/locustfile.py" ]]; then
    echo "locustfile.py not found at $REPO_ROOT/locustfile.py" >&2
    exit 1
fi

HOST="${1:-http://127.0.0.1:8001}"

# Web UI port: set LOCUST_WEB_PORT=8090 to force a port; otherwise first free in 8089-8092.
pick_web_port() {
    if [ -n "${LOCUST_WEB_PORT:-}" ]; then
        if lsof -i ":${LOCUST_WEB_PORT}" >/dev/null 2>&1; then
            echo "Port ${LOCUST_WEB_PORT} is already in use. Free it or pick another:" >&2
            lsof -i ":${LOCUST_WEB_PORT}" >&2
            echo "Example: LOCUST_WEB_PORT=8090 $0 $HOST" >&2
            exit 1
        fi
        echo "${LOCUST_WEB_PORT}"
        return
    fi
    local p
    for p in 8089 8090 8091 8092; do
        if ! lsof -i ":$p" >/dev/null 2>&1; then
            echo "$p"
            return
        fi
    done
    echo "No free port in 8089-8092. Stop other Locust instances or set LOCUST_WEB_PORT." >&2
    exit 1
}

WEB_PORT="$(pick_web_port)"

# Install locust if missing
if ! python3 -c "import locust" 2>/dev/null; then
    echo "Installing locust..."
    pip install locust
fi

echo "Starting Locust with host=$HOST"
echo "Open the Locust web UI at: http://localhost:${WEB_PORT}"
echo "If you're on a remote server, use: http://YOUR_SERVER_IP:${WEB_PORT}"
echo ""

# Bind to 0.0.0.0 so you can access from another machine (e.g. browser on your laptop)
exec locust -f "$REPO_ROOT/locustfile.py" --host="$HOST" --web-host=0.0.0.0 --web-port="${WEB_PORT}"
