#!/usr/bin/env python3
"""仅补算新股 RS（不重复主 RS）。主 RS 已存在但新股榜为空时使用。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.stock_rs import backfill_new_stock_rs_for_snapshot
from src.storage import Storage


def main() -> int:
    parser = argparse.ArgumentParser(description="补算新股 RS 并更新观察名单")
    parser.add_argument("--date", help="快照日期 YYYY-MM-DD，默认最新")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    storage = Storage(db_path(config))
    snapshot_date = args.date or storage.get_latest_date()
    if not snapshot_date:
        print("尚无行业快照，请先运行 run_daily.py")
        return 1
    if not storage.get_stock_rs_raw(snapshot_date):
        print(f"{snapshot_date} 尚无主 RS，请先刷新个股 RS")
        return 1

    print(f"补算新股 RS：{snapshot_date} …")

    def _progress(done: int, total: int) -> None:
        if total > 0 and done % 50 == 0:
            print(f"  拉价进度 {done}/{total}")

    result = backfill_new_stock_rs_for_snapshot(
        storage,
        snapshot_date,
        config,
        progress_callback=_progress,
    )
    print(
        "完成："
        f"拉取 {result.get('fetched_symbols', 0)}，"
        f"有效bar {result.get('bars_for_new_rs', 0)}，"
        f"新股榜 {result.get('new_stock_leaderboard_count', 0)}，"
        f"观察名单 {result.get('watchlist_count', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
