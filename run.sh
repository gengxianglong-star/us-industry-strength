#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source ".venv/bin/activate"
python -m pip install --upgrade pip
pip install -r requirements.txt

MODE="${1:-serve}"
if [ "$MODE" = "daily" ]; then
  python scripts/precompute_daily.py
elif [ "$MODE" = "breadth" ]; then
  python scripts/sync_breadth.py
  exit 0
fi

exec python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
