#!/usr/bin/env bash
# Export dashboard JSON from local SQLite and zip for GitHub Release upload.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FULL_BREADTH=0
for arg in "$@"; do
  case "$arg" in
    --full-breadth) FULL_BREADTH=1 ;;
  esac
done

if [ "$FULL_BREADTH" = "1" ]; then
  echo "Running full breadth sync (may take a few minutes)…"
  .venv/bin/python scripts/sync_breadth.py --full
fi

echo "Exporting dashboard JSON from local database…"
.venv/bin/python scripts/export_public_dashboard.py

OUT_ZIP="$ROOT_DIR/dashboard-data.zip"
rm -f "$OUT_ZIP"
(
  cd frontend/public/data
  zip -q -r "$OUT_ZIP" .
)

echo ""
echo "Created: $OUT_ZIP"
echo ""
echo "Upload to GitHub, then run the Pages workflow with skip precompute:"
echo "  gh release upload dashboard-data \"$OUT_ZIP\" --clobber"
echo "  gh workflow run pages.yml -f skip_precompute=true"
echo ""
echo "Or create the release tag first if missing:"
echo "  gh release create dashboard-data \"$OUT_ZIP\" --title \"Dashboard data\" --notes \"Local export\""
