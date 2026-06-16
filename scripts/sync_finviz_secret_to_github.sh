#!/usr/bin/env bash
# Verify local FINVIZ_AUTH_KEY then push to GitHub Actions secrets.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: install GitHub CLI first — https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: run 'gh auth login' first" >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "ERROR: create .env with FINVIZ_AUTH_KEY=your_elite_api_token" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Verifying Elite CSV exports with local .env …"
python scripts/verify_finviz_elite_exports.py

KEY="$(
  python - <<'PY'
from dotenv import dotenv_values
key = (dotenv_values(".env").get("FINVIZ_AUTH_KEY") or "").strip()
if not key:
    raise SystemExit("FINVIZ_AUTH_KEY missing or empty in .env")
print(key, end="")
PY
)"

printf '%s' "$KEY" | gh secret set FINVIZ_AUTH_KEY --repo "$(gh repo view --json nameWithOwner -q .nameWithOwner)"
echo ""
echo "Done: GitHub secret FINVIZ_AUTH_KEY updated."
echo "Re-run workflow: gh workflow run pages.yml"
