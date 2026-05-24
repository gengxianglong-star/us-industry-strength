"""Re-score an existing snapshot using stored performance data."""

from __future__ import annotations

from typing import Any

from src.finviz_scraper import IndustryRow
from src.scoring import score_industries
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
) -> int:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise ValueError(f"未找到快照 {snapshot_date}")

    industry_rows = rows_from_snapshot(rows)
    scored = score_industries(industry_rows, config)
    storage.save_snapshot(snapshot_date, scored)
    return len(scored)
