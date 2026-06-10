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
from src.services.daily_jobs import DailyJobService, daily_options_from_config
from src.storage import Storage, latest_trading_date


def main() -> int:
    parser = argparse.ArgumentParser(description="运行每日预计算任务")
    parser.add_argument("--date", help="快照日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--skip-rs", action="store_true")
    parser.add_argument(
        "--skip-screener",
        "--skip-stocks",
        action="store_true",
        dest="skip_stocks",
        help="跳过 Top 行业 Finviz 筛股（只跑行业+RS 等后续步骤）",
    )
    parser.add_argument("--skip-breadth", action="store_true")
    parser.add_argument("--full-breadth", action="store_true")
    parser.add_argument(
        "--sync-rs",
        action="store_true",
        help="Run RS inline (required before static export)",
    )
    parser.add_argument("--force", action="store_true", help="忽略已有完成状态，强制重跑")
    parser.add_argument(
        "--force-full-rs",
        action="store_true",
        help="Disable RS incremental mode — recompute entire universe",
    )
    args = parser.parse_args()

    config = load_config()
    storage = Storage(db_path(config))
    snapshot_date = args.date or latest_trading_date()
    service = DailyJobService()

    print(f"[precompute] snapshot_date={snapshot_date}")
    if not args.force:
        status = service.get_status(storage, config, snapshot_date)
        if status.get("daily_status") in {"ready", "degraded"}:
            print(f"[precompute] skipped: already {status.get('daily_status')}")
            print(f"[precompute] headline: {status.get('headline')}")
            return 0

    try:
        opts = daily_options_from_config(config)
        if args.skip_rs:
            opts.skip_rs = True
        if args.skip_stocks:
            opts.skip_stocks = True
        if args.skip_breadth:
            opts.skip_breadth = True
        if args.full_breadth:
            opts.full_breadth = True
        if args.sync_rs:
            opts.rs_async = False
        if args.force_full_rs:
            opts.force_full_rs = True
        service.run_sync(
            storage,
            config,
            snapshot_date,
            options=opts,
        )
        print("[precompute] done")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[precompute] failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
