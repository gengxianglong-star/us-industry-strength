"""Snapshot response assembly and ranking helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.scoring import top_strong_sort_key
from src.storage import Storage


@dataclass
class SnapshotIndustry:
    key: str
    score: float
    rank_m: int
    rank_q: int
    tags: list[str]
    excluded: bool


def to_snapshot_industries(rows: list[dict[str, Any]]) -> list[SnapshotIndustry]:
    return [
        SnapshotIndustry(
            key=str(r["industry_key"]),
            score=float(r.get("score") or 0),
            rank_m=int(r.get("rank_m") or 9999),
            rank_q=int(r.get("rank_q") or 9999),
            tags=list(r.get("tags") or []),
            excluded=bool(r.get("excluded")),
        )
        for r in rows
    ]


def _row_top_sort_key(row: dict[str, Any]) -> tuple[float, int, int, str]:
    return top_strong_sort_key(
        float(row.get("score") or 0),
        int(row.get("rank_m") or 9999),
        int(row.get("rank_q") or 9999),
        str(row.get("industry_key") or ""),
    )


def scored_industries_from_rows(rows: list[dict[str, Any]]) -> list[SnapshotIndustry]:
    active = [x for x in to_snapshot_industries(rows) if not x.excluded]
    active.sort(key=lambda x: top_strong_sort_key(x.score, x.rank_m, x.rank_q, x.key))
    return active


def top_strong_from_rows(
    rows: list[dict[str, Any]],
    *,
    top_n: int,
    stock_picks: dict[str, Any] | None = None,
) -> list[SnapshotIndustry]:
    active = [r for r in rows if not r.get("excluded")]
    active.sort(key=_row_top_sort_key)
    if stock_picks is None:
        return to_snapshot_industries(active[:top_n])
    selected: list[dict[str, Any]] = []
    for row in active:
        if len(selected) >= top_n:
            break
        pick = stock_picks.get(row["industry_key"]) or {}
        tickers = pick.get("tickers") or []
        if tickers:
            selected.append(row)
    return to_snapshot_industries(selected)


def core_strong_from_rows(rows: list[dict[str, Any]], *, top_n: int) -> list[SnapshotIndustry]:
    active = [x for x in to_snapshot_industries(rows) if not x.excluded]
    core = [x for x in active if "Core" in x.tags]
    core.sort(key=lambda x: top_strong_sort_key(x.score, x.rank_m, x.rank_q, x.key))
    return core[:top_n]


def build_snapshot_response(
    *,
    storage: Storage,
    snapshot_date: str,
    rows: list[dict[str, Any]],
    top_n: int,
) -> dict[str, Any]:
    active = [r for r in rows if not r["excluded"]]
    stock_picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    core_keys = {x.key for x in core_strong_from_rows(active, top_n=top_n)}
    top_keys = {
        x.key
        for x in top_strong_from_rows(active, top_n=top_n, stock_picks=stock_picks)
    }
    deltas = storage.compare_all_with_previous(snapshot_date)

    for row in rows:
        row["is_core"] = row["industry_key"] in core_keys
        row["is_top_strong"] = row["industry_key"] in top_keys
        row["vs_previous"] = deltas.get(row["industry_key"])
        pick = stock_picks.get(row["industry_key"])
        if pick:
            row["stock_picks"] = pick["tickers"]
            row["stock_screener_url"] = pick.get("screener_url")
            row["stock_picks_error"] = pick.get("error")
            row["stock_picks_stale_fallback"] = str(pick.get("error") or "").startswith(
                "沿用缓存("
            )
        else:
            row["stock_picks"] = []
            row["stock_screener_url"] = None
            row["stock_picks_error"] = None
            row["stock_picks_stale_fallback"] = False

    rs_count = storage.count_stock_rs(snapshot_date)
    rs_watchlist_count = storage.count_stock_watchlist(snapshot_date)
    rs_watchlist = storage.get_stock_watchlist(snapshot_date, limit=50)
    rs_meta = storage.get_stock_rs_meta(snapshot_date)
    run_status = storage.get_snapshot_run(snapshot_date)

    return {
        "snapshot_date": snapshot_date,
        "industry_count": len(rows),
        "core_count": len(core_keys),
        "top_strong_count": len(top_keys),
        "rs_count": rs_count,
        "rs_watchlist_count": rs_watchlist_count,
        "rs_meta": rs_meta,
        "run_status": run_status,
        "watchlist_preview": rs_watchlist,
        "industries": rows,
    }

