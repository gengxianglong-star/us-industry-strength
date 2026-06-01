#!/usr/bin/env bash
# Start local server if needed, trigger automation ensure, open the dashboard in a browser.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p "${ROOT_DIR}/logs"

PORT="${DASHBOARD_PORT:-8080}"
BASE_URL="http://127.0.0.1:${PORT}"
HEALTH_URL="${BASE_URL}/api/health?quick=1"
OPEN_URL="${BASE_URL}/strong"
LABEL="gui/$(id -u)/com.us-industry-strength.server"
PLIST="${HOME}/Library/LaunchAgents/com.us-industry-strength.server.plist"
LOG_FILE="${ROOT_DIR}/logs/open-dashboard.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >>"$LOG_FILE"
}

server_up() {
  curl -sf "$HEALTH_URL" >/dev/null 2>&1
}

start_server() {
  if [[ -f "$PLIST" ]]; then
    log "kickstart launchd ${LABEL}"
    launchctl kickstart -k "$LABEL" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    return
  fi
  if [[ -x "${ROOT_DIR}/run.sh" ]]; then
    log "launch run.sh serve (no launchd plist)"
    nohup "${ROOT_DIR}/run.sh" serve >>"${LOG_FILE}" 2>&1 &
    return
  fi
  log "error: cannot start server (missing launchd + run.sh)"
  exit 1
}

wait_for_server() {
  for _ in $(seq 1 45); do
    if server_up; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if ! server_up; then
  start_server
  if ! wait_for_server; then
    log "error: server did not become healthy"
    osascript -e 'display alert "US Industry Strength" message "本地服务未能启动。请检查 logs/open-dashboard.log"' >/dev/null 2>&1 || true
    exit 1
  fi
fi

curl -sf -X POST "${BASE_URL}/api/automation/ensure" >/dev/null 2>&1 || true
log "open ${OPEN_URL}"

BROWSER="${OPEN_DASHBOARD_BROWSER:-Microsoft Edge}"
if ! open -a "$BROWSER" "$OPEN_URL" 2>/dev/null; then
  open "$OPEN_URL"
fi
