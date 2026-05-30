#!/usr/bin/env bash
# Upload dashboard-data.zip to GitHub Release and trigger Pages publish.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ORACLE_ENV_FILE:-$ROOT_DIR/.oracle.env}"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "ERROR: GITHUB_TOKEN not set. Copy scripts/oracle/env.example to .oracle.env" >&2
  exit 1
fi

REPO="${GITHUB_REPO:-gengxianglong-star/us-industry-strength}"
ZIP="$ROOT_DIR/dashboard-data.zip"

if [ ! -f "$ZIP" ]; then
  echo "ERROR: $ZIP not found — run package_pages_data.sh first" >&2
  exit 1
fi

export GH_TOKEN="$GITHUB_TOKEN"

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI not installed" >&2
  exit 1
fi

NOTES="Oracle VM auto export $(date -u +%Y-%m-%dT%H:%M:%SZ)"

if gh release view dashboard-data -R "$REPO" >/dev/null 2>&1; then
  gh release upload dashboard-data "$ZIP" -R "$REPO" --clobber
  gh release edit dashboard-data -R "$REPO" --notes "$NOTES"
  echo "[publish] updated release dashboard-data"
else
  gh release create dashboard-data "$ZIP" -R "$REPO" \
    --title "Dashboard data" \
    --notes "$NOTES"
  echo "[publish] created release dashboard-data"
fi

gh workflow run pages.yml -R "$REPO" -f skip_precompute=true
echo "[publish] triggered pages.yml (skip_precompute=true)"
