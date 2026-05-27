"""Re-score an existing snapshot using stored performance data."""

from __future__ import annotations

from typing import Any

from src.finviz_scraper import IndustryRow
from src.scoring import score_industries
from src.services.snapshots import scored_industries_from_rows
from src.stock_rs import rebuild_stock_watchlist_for_snapshot
from src.storage import Storage


def rows_from_snapshot(snapshot_rows: list[dict[str, Any]]) -> list[IndustryRow]:
    return [
        IndustryRow(
            key=row["industry_key"],
            name=row["name"],
            stocks=int(row["stocks"]),
            perf_w=float(row["perf_w"]),
            perf_m=float(row["perf_m"]),
            perf_q=float(row["perf_q"]),
            perf_h=float(row["perf_h"]),
            perf_y=float(row["perf_y"]),
            finviz_url=row.get("finviz_url") or "",
        )
        for row in snapshot_rows
    ]


def rescore_snapshot(
    storage: Storage,
    snapshot_date: str,
    config: dict[str, Any],
    *,
    rebuild_watchlist: bool = True,
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise ValueError(f"未找到快照 {snapshot_date}")

    industry_rows = rows_from_snapshot(rows)
    scored = score_industries(industry_rows, config)
    storage.save_snapshot(snapshot_date, scored)

    watchlist_count: int | None = None
    if rebuild_watchlist and storage.count_stock_rs(snapshot_date) > 0:
        info = rebuild_stock_watchlist_for_snapshot(
            storage,
            snapshot_date,
            scored_industries_from_rows(storage.get_snapshot(snapshot_date)),
            config,
        )
        watchlist_count = int(info.get("watchlist_count", 0) or 0)
    return {"industry_count": len(scored), "watchlist_count": watchlist_count}
