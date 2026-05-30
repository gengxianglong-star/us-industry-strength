#!/usr/bin/env python3
"""Fetch Finviz data, score industries, and save daily snapshot (no breadth)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.services.daily_jobs import DailyJobService, daily_options_from_config
from src.storage import Storage, latest_trading_date


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 Finviz 行业数据并写入快照")
    parser.add_argument("--date", help="快照日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--skip-stocks", action="store_true")
    parser.add_argument("--skip-rs", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    snapshot_date = args.date or latest_trading_date()
    storage = Storage(db_path(config))
    service = DailyJobService()

    opts = daily_options_from_config(config)
    if args.skip_stocks:
        opts.skip_stocks = True
    if args.skip_rs:
        opts.skip_rs = True
    opts.skip_breadth = True
    try:
        result = service.run_sync(
            storage,
            config,
            snapshot_date,
            options=opts,
        )
        print(f"快照已保存: {snapshot_date}（Top {result.get('top_count', 0)} 行业）")
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
