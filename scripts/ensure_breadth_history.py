#!/usr/bin/env python3
"""Backfill breadth history when the local DB is too shallow for charts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.storage import Storage


def main() -> int:
    config = load_config()
    storage = Storage(db_path(config))
    rows = storage.get_breadth_daily(limit=15000)
    if not rows:
        print("[breadth] no rows — running full sync")
        from src.breadth_data import sync_breadth_history

        sync_breadth_history(storage, full=True, config=config)
        return 0

    dates = [str(r["trade_date"]) for r in rows]
    oldest = min(dates)
    count = len(rows)
    print(f"[breadth] cached rows={count} oldest={oldest} newest={max(dates)}")
    if count >= 1500 and oldest <= "2018-01-01":
        print("[breadth] history looks sufficient — skip full sync")
        return 0

    print("[breadth] history shallow — running full sync")
    from src.breadth_data import sync_breadth_history

    sync_breadth_history(storage, full=True, config=config)
    after = storage.get_breadth_daily(limit=15000)
    after_dates = [str(r["trade_date"]) for r in after]
    print(f"[breadth] after full sync rows={len(after)} oldest={min(after_dates) if after_dates else '—'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
