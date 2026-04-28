#!/usr/bin/env bash
# Deploy backend to production over SSH/rsync.
#
# Setup once:
#   cp scripts/deploy.env.example scripts/deploy.env
#   # Edit scripts/deploy.env — set DEPLOY_PASSWORD='...' if using password auth,
#   # or rely on SSH keys (~/.ssh) and omit DEPLOY_PASSWORD.
#
# Run from repo root:
#   ./scripts/deploy.sh
#
# Installs: rsync, ssh; for password login also: sshpass (macOS: brew install sshpass)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "$SCRIPT_DIR/deploy.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/deploy.env"
  set +a
fi

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST="${DEPLOY_HOST:-72.61.148.117}"
DEPLOY_REMOTE_PATH="${DEPLOY_REMOTE_PATH:-/root/fight}"
DEPLOY_SYSTEMD_SERVICE="${DEPLOY_SYSTEMD_SERVICE:-fight}"

REMOTE="${DEPLOY_USER}@${DEPLOY_HOST}"

RSYNC_EXCLUDES=(
  --exclude='venv/'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='media/'
  --exclude='db.sqlite3'
  --exclude='.env'
  --exclude='*.sqlite3'
  --exclude='staticfiles/'
)

_ssh() {
  if [[ -n "${DEPLOY_PASSWORD:-}" ]]; then
    if ! command -v sshpass &>/dev/null; then
      echo "DEPLOY_PASSWORD is set but sshpass is not installed." >&2
      echo "Install: brew install sshpass   or   apt install sshpass" >&2
      exit 1
    fi
    SSHPASS="$DEPLOY_PASSWORD" sshpass -e ssh -o StrictHostKeyChecking=accept-new "$@"
  else
    ssh -o StrictHostKeyChecking=accept-new "$@"
  fi
}

_rsync() {
  if [[ -n "${DEPLOY_PASSWORD:-}" ]]; then
    SSHPASS="$DEPLOY_PASSWORD" sshpass -e rsync -avz \
      "${RSYNC_EXCLUDES[@]}" \
      -e 'ssh -o StrictHostKeyChecking=accept-new' \
      "$@"
  else
    rsync -avz \
      "${RSYNC_EXCLUDES[@]}" \
      -e 'ssh -o StrictHostKeyChecking=accept-new' \
      "$@"
  fi
}

echo "==> Deploy backend/ -> ${REMOTE}:${DEPLOY_REMOTE_PATH}/"
_rsync backend/ "${REMOTE}:${DEPLOY_REMOTE_PATH}/"

if [[ -n "${DEPLOY_SYSTEMD_SERVICE}" ]]; then
  REMOTE_PYTHON="${DEPLOY_REMOTE_PYTHON:-${DEPLOY_REMOTE_PATH}/venv/bin/python3}"

  echo "==> Run migrations"
  _ssh "$REMOTE" "cd ${DEPLOY_REMOTE_PATH} && ${REMOTE_PYTHON} manage.py migrate --noinput"

  echo "==> Restart systemd: ${DEPLOY_SYSTEMD_SERVICE}"
  _ssh "$REMOTE" "systemctl restart ${DEPLOY_SYSTEMD_SERVICE} && systemctl is-active ${DEPLOY_SYSTEMD_SERVICE}"
fi

echo "==> Done."
