#!/usr/bin/env bash
# Full cloud daily: precompute → export → GitHub Pages publish.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/oracle-daily-$(date +%Y%m%d).log"

exec >>"$LOG_FILE" 2>&1
echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) oracle daily_pipeline ====="

ENV_FILE="${ORACLE_ENV_FILE:-$ROOT_DIR/.oracle.env}"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source ".venv/bin/activate"

echo "[daily] ensure breadth history (full sync if shallow)…"
python scripts/ensure_breadth_history.py || true

echo "[daily] precompute (sync RS)…"
python scripts/precompute_daily.py --sync-rs

echo "[daily] export + zip…"
bash scripts/package_pages_data.sh

echo "[daily] publish to GitHub Pages…"
bash scripts/oracle/publish_pages.sh

echo "===== done $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
