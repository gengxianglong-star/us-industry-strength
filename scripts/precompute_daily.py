#!/usr/bin/env python3
"""每日预计算：行业快照 + Top行业个股 + 全市场RS + 市场宽度。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.breadth_data import sync_breadth_history
from src.config_loader import db_path, load_config
from src.finviz_scraper import fetch_industries
from src.scoring import filter_top_strong, score_industries
from src.stock_rs import compute_and_store_stock_rs
from src.stock_picks import fetch_top_industry_stock_picks
from src.storage import Storage, today_snapshot_date


def main() -> int:
    parser = argparse.ArgumentParser(description="运行每日预计算任务")
    parser.add_argument("--date", help="快照日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--skip-rs", action="store_true", help="跳过全市场RS")
    parser.add_argument("--skip-breadth", action="store_true", help="跳过市场宽度同步")
    parser.add_argument("--full-breadth", action="store_true", help="宽度执行全量重建")
    args = parser.parse_args()

    config = load_config()
    storage = Storage(db_path(config))
    snapshot_date = args.date or today_snapshot_date()

    print(f"[precompute] snapshot_date={snapshot_date}")
    storage.upsert_snapshot_run(
        snapshot_date,
        "running",
        current_step="industry_fetch",
        details={
            "skip_rs": bool(args.skip_rs),
            "skip_breadth": bool(args.skip_breadth),
            "full_breadth": bool(args.full_breadth),
        },
    )
    try:
        rows = fetch_industries(config)
        scored = score_industries(rows, config)
        top = filter_top_strong(scored, config)
        storage.save_snapshot(snapshot_date, scored)
        print(f"[precompute] industries={len(rows)} top={len(top)}")
        storage.upsert_snapshot_run(
            snapshot_date,
            "running",
            current_step="stock_picks",
            details={"industries": len(rows), "top": len(top)},
        )

        picks = fetch_top_industry_stock_picks(storage, snapshot_date, scored, config)
        picked_total = sum(len(v.get("tickers") or []) for v in picks.values())
        pick_errors = sum(1 for v in picks.values() if v.get("error"))
        print(
            f"[precompute] stock_picks industries={len(picks)} "
            f"tickers={picked_total} errors={pick_errors}"
        )

        rs: dict[str, object] = {}
        if not args.skip_rs:
            storage.upsert_snapshot_run(snapshot_date, "running", current_step="stock_rs")
            rs = compute_and_store_stock_rs(storage, snapshot_date, scored, config)
            print(
                "[precompute] rs "
                f"universe={rs.get('universe_count', 0)} "
                f"computed={rs.get('computed_count', 0)} "
                f"new_lb={rs.get('new_stock_leaderboard_count', 0)} "
                f"watchlist={rs.get('watchlist_count', 0)}"
            )

        br: dict[str, object] = {}
        if not args.skip_breadth:
            storage.upsert_snapshot_run(snapshot_date, "running", current_step="breadth_sync")
            br = sync_breadth_history(storage, full=args.full_breadth)
            validation = br.get("validation") or {}
            print(
                "[precompute] breadth "
                f"mode={br.get('mode')} merged={br.get('merged_row_count', 0)} "
                f"validation_ok={validation.get('ok')}"
            )
            if not bool(validation.get("ok", True)):
                raise RuntimeError("breadth validation failed")

        storage.upsert_snapshot_run(
            snapshot_date,
            "completed",
            current_step="done",
            details={
                "industry_count": len(rows),
                "top_count": len(top),
                "stock_pick_count": picked_total,
                "stock_pick_errors": pick_errors,
                "rs_computed_count": int(rs.get("computed_count", 0) or 0),
                "breadth_merged_count": int(br.get("merged_row_count", 0) or 0),
            },
            finished=True,
        )
        print("[precompute] done")
        return 0
    except Exception as exc:  # noqa: BLE001
        storage.upsert_snapshot_run(
            snapshot_date,
            "failed",
            current_step="failed",
            error=str(exc),
            finished=True,
        )
        print(f"[precompute] failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

