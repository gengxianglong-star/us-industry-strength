#!/usr/bin/env bash
# 每日任务：预计算（行业快照 + Top行业个股 + RS + 市场宽度）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/scheduled-$(date +%Y%m%d).log"

exec >>"$LOG_FILE" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') scheduled_daily ====="

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source ".venv/bin/activate"

python scripts/precompute_daily.py

echo "===== done $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
