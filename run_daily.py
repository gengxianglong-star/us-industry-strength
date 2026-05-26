#!/usr/bin/env python3
"""Fetch Finviz data, score industries, and save daily snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.finviz_scraper import fetch_industries
from src.scoring import filter_core_strong, filter_top_strong, score_industries
from src.stock_rs import compute_and_store_stock_rs
from src.stock_picks import fetch_top_industry_stock_picks
from src.storage import Storage, today_snapshot_date


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 Finviz 行业数据并写入快照")
    parser.add_argument(
        "--date",
        help="快照日期 YYYY-MM-DD，默认今天",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config.yaml",
        help="配置文件路径",
    )
    parser.add_argument(
        "--skip-stocks",
        action="store_true",
        help="跳过核心行业的个股筛选抓取",
    )
    parser.add_argument(
        "--skip-rs",
        action="store_true",
        help="跳过个股相对强度（RS）计算",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    snapshot_date = args.date or today_snapshot_date()
    storage = Storage(db_path(config))

    storage.upsert_snapshot_run(
        snapshot_date,
        "running",
        current_step="industry_fetch",
        details={"skip_stocks": bool(args.skip_stocks), "skip_rs": bool(args.skip_rs)},
    )
    try:
        print(f"正在抓取 Finviz 行业数据…")
        rows = fetch_industries(config)
        print(f"共获取 {len(rows)} 个行业")

        scored = score_industries(rows, config)
        top = filter_top_strong(scored, config)
        storage.save_snapshot(snapshot_date, scored)
        storage.upsert_snapshot_run(
            snapshot_date, "running", current_step="stock_picks", details={"top_count": len(top)}
        )

        if not args.skip_stocks and top:
            print(f"正在抓取 Top {len(top)} 强势行业的筛选个股…")
            picks = fetch_top_industry_stock_picks(storage, snapshot_date, scored, config)
            for key, payload in picks.items():
                name = next((c.name for c in top if c.key == key), key)
                tickers = payload.get("tickers", [])
                err = payload.get("error")
                if err:
                    print(f"  {name}: 失败 ({err})")
                else:
                    print(f"  {name} ({len(tickers)}): {', '.join(tickers) if tickers else '（无匹配）'}")

        rs_result: dict[str, Any] = {}
        if not args.skip_rs:
            storage.upsert_snapshot_run(snapshot_date, "running", current_step="stock_rs")
            print("正在计算全市场个股相对强度（RS）并生成交叉观察名单…")
            rs_result = compute_and_store_stock_rs(storage, snapshot_date, scored, config)
            print(
                "RS 完成："
                f"Universe={rs_result['universe_count']} "
                f"Computed={rs_result['computed_count']} "
                f"NewLeaderboard={rs_result.get('new_stock_leaderboard_count', 0)} "
                f"Watchlist={rs_result['watchlist_count']}"
            )

        storage.upsert_snapshot_run(
            snapshot_date,
            "completed",
            current_step="done",
            details={
                "industry_count": len(rows),
                "top_count": len(top),
                "rs_computed_count": int(rs_result.get("computed_count", 0) or 0),
            },
            finished=True,
        )
        print(f"快照已保存: {snapshot_date}")
        print(f"强势行业 Top {len(top)}:")
        for item in top:
            print(
                f"  {item.name:40} score={item.score:.3f} "
                f"rank(M/Q/H)={item.rank_m}/{item.rank_q}/{item.rank_h} stocks={item.stocks}"
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        storage.upsert_snapshot_run(
            snapshot_date,
            "failed",
            current_step="failed",
            error=str(exc),
            finished=True,
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
