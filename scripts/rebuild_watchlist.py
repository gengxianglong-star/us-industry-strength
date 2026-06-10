#!/usr/bin/env python3
"""Rebuild stock watchlist for the latest (or given) snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.services.snapshots import scored_industries_from_rows
from src.stock_rs import enrich_catalysts_for_snapshot, rebuild_stock_watchlist_for_snapshot
from src.storage import Storage


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild stock watchlist from stored RS rows.")
    parser.add_argument("--date", help="Snapshot date (YYYY-MM-DD). Defaults to latest.")
    parser.add_argument("--export", action="store_true", help="Export public dashboard JSON after rebuild.")
    args = parser.parse_args()

    config = load_config()
    storage = Storage(db_path(config))
    snapshot_date = args.date or storage.get_latest_date()
    if not snapshot_date:
        print("No snapshot in database.", file=sys.stderr)
        return 1
    if storage.count_stock_rs(snapshot_date) <= 0:
        print(f"No RS rows for {snapshot_date}. Run RS compute first.", file=sys.stderr)
        return 1

    scored = scored_industries_from_rows(storage.get_snapshot(snapshot_date))
    print(f"Rebuilding watchlist for {snapshot_date} …")
    info = rebuild_stock_watchlist_for_snapshot(storage, snapshot_date, scored, config)
    count = int(info.get("watchlist_count", 0) or storage.count_stock_watchlist(snapshot_date))
    print(f"Done: watchlist_count={count}")

    print("Running catalyst enrichment on final watchlist…")
    cat = enrich_catalysts_for_snapshot(storage, snapshot_date, config)
    print(
        f"Catalysts: {cat.get('tagged_count', 0)}/{cat.get('candidate_count', 0)} tagged "
        f"(skipped={cat.get('skipped')})"
    )

    preview = storage.get_stock_watchlist(snapshot_date, limit=10)
    for row in preview:
        industry = (row.get("industries") or [""])[0]
        tag = (row.get("catalyst") or {}).get("tag")
        tag_suffix = f"  [{tag}]" if tag else ""
        print(f"  #{row['rs_rank']} {row['symbol']} RS={float(row['rs_score']):.3f} {industry}{tag_suffix}")

    if args.export and count > 0:
        import subprocess

        print("Exporting dashboard JSON …")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "export_public_dashboard.py")],
            check=True,
            cwd=str(ROOT),
        )

    return 0 if count > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
