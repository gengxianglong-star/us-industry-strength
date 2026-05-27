#!/usr/bin/env python3
"""Fetch Finviz data, score industries, and save daily snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.pipeline.daily import DailyPipelineOptions, run_daily_pipeline
from src.storage import Storage, today_snapshot_date


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 Finviz 行业数据并写入快照")
    parser.add_argument("--date", help="快照日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--skip-stocks", action="store_true")
    parser.add_argument("--skip-rs", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    snapshot_date = args.date or today_snapshot_date()
    storage = Storage(db_path(config))

    try:
        result = run_daily_pipeline(
            storage,
            config,
            snapshot_date,
            DailyPipelineOptions(
                skip_stocks=args.skip_stocks,
                skip_rs=args.skip_rs,
                skip_breadth=True,
                verbose=True,
            ),
        )
        print(f"快照已保存: {snapshot_date}（Top {result.get('top_count', 0)} 行业）")
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
