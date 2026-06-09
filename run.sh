#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

MODE="${1:-serve}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  NEED_PIP=1
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"

if [ "${NEED_PIP:-0}" = "1" ] || [ "$MODE" = "setup" ] || [ "${RUN_PIP_INSTALL:-0}" = "1" ]; then
  python -m pip install --upgrade pip
  pip install -r requirements.txt
fi

if [ "$MODE" = "install" ]; then
  bash scripts/install-automation.sh
  exit 0
fi
if [ "$MODE" = "setup" ]; then
  echo "依赖已安装。"
  exit 0
fi
if [ "$MODE" = "daily" ]; then
  python scripts/precompute_daily.py
  exit 0
fi
if [ "$MODE" = "breadth" ]; then
  python scripts/sync_breadth.py
  exit 0
fi

build_frontend() {
  if [ ! -f frontend/package.json ]; then
    return 0
  fi
  local npm_cmd="npm"
  if ! command -v npm >/dev/null 2>&1; then
    local bundled
    bundled="$(find "$ROOT_DIR/.tools" -maxdepth 2 -type f -name npm 2>/dev/null | head -1)"
    if [ -n "$bundled" ]; then
      export PATH="$(dirname "$bundled"):$PATH"
      npm_cmd="$bundled"
    else
      echo "warning: npm not found — skip frontend build (legacy web/ served if no web/dist)" >&2
      return 0
    fi
  fi
  echo "Exporting dashboard JSON (watchlist chart bars)…"
  python scripts/export_public_dashboard.py

  echo "Building frontend…"
  (cd frontend && "$npm_cmd" install --no-audit --no-fund && "$npm_cmd" run build)
}

if [ "${SKIP_FRONTEND_BUILD:-0}" != "1" ]; then
  build_frontend
fi

exec python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
