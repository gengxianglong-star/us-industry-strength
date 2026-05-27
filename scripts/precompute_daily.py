#!/usr/bin/env python3
"""每日预计算：行业快照 + Top行业个股 + 全市场RS + 市场宽度。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.pipeline.daily import DailyPipelineOptions, run_daily_pipeline
from src.storage import Storage, today_snapshot_date


def main() -> int:
    parser = argparse.ArgumentParser(description="运行每日预计算任务")
    parser.add_argument("--date", help="快照日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--skip-rs", action="store_true")
    parser.add_argument("--skip-breadth", action="store_true")
    parser.add_argument("--full-breadth", action="store_true")
    args = parser.parse_args()

    config = load_config()
    storage = Storage(db_path(config))
    snapshot_date = args.date or today_snapshot_date()

    print(f"[precompute] snapshot_date={snapshot_date}")
    try:
        run_daily_pipeline(
            storage,
            config,
            snapshot_date,
            DailyPipelineOptions(
                skip_breadth=args.skip_breadth,
                skip_rs=args.skip_rs,
                full_breadth=args.full_breadth,
                verbose=True,
            ),
        )
        print("[precompute] done")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[precompute] failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
