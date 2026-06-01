#!/usr/bin/env bash
# Local full refresh: breadth history → daily precompute (sync RS) → export zip.
# Same steps as scripts/oracle/daily_pipeline.sh minus GitHub publish.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/local-full-$(date +%Y%m%d-%H%M%S).log"

exec >>"$LOG_FILE" 2>&1
echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) local_full_pipeline ====="
echo "Log: $LOG_FILE"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  python3 -m pip install --upgrade pip
  pip install -r requirements.txt
fi
# shellcheck disable=SC1091
source ".venv/bin/activate"

echo "[1/3] full breadth sync…"
python scripts/sync_breadth.py --full

echo "[2/3] precompute (sync RS, force full universe)…"
python scripts/precompute_daily.py --sync-rs --force --force-full-rs

echo "[3/3] export + zip…"
bash scripts/package_pages_data.sh

echo "===== done $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
echo "Open http://127.0.0.1:8080/strong after ./run.sh serve"
