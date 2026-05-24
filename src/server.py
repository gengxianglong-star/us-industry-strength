"""FastAPI server for industry strength dashboard."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from src.config_loader import (
    DEFAULT_CONFIG_PATH,
    db_path,
    get_editable_config,
    load_config,
    save_editable_config,
)
from src.config_models import ConfigUpdate
from src.breadth_data import load_breadth_data
from src.rescore import rescore_snapshot
from src.stock_rs import compute_and_store_stock_rs
from src.stock_picks import fetch_and_store_stock_picks
from src.storage import Storage

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="US Industry Strength")
config = load_config()
storage = Storage(db_path(config))
RS_PROGRESS: dict[str, dict[str, Any]] = {}
RS_PROGRESS_LOCK = threading.Lock()


def _reload_config() -> None:
    global config
    config = load_config()


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    editable = get_editable_config(config)
    weights = editable["weights"]
    total = sum(float(weights.get(k, 0)) for k in weights)
    editable["weights_normalized"] = {
        k: round(float(weights.get(k, 0)) / total, 4) if total else 0
        for k in weights
    }
    return editable


@app.get("/api/breadth")
def get_breadth_data(
    refresh: bool = Query(default=False),
    limit: int = Query(default=180, ge=10, le=2000),
) -> dict[str, Any]:
    payload = load_breadth_data(force_refresh=refresh)
    return {
        **payload,
        "rows": payload["rows"][:limit],
        "row_count": len(payload["rows"]),
        "limit": limit,
    }


@app.put("/api/config")
def update_config(body: ConfigUpdate) -> dict[str, Any]:
    if body.thresholds.tier_b_score > body.thresholds.tier_a_score:
        raise HTTPException(
            status_code=400,
            detail="tier_b_score 不能大于 tier_a_score",
        )

    weight_total = sum(
        getattr(body.weights, field) for field in body.weights.model_fields
    )
    if weight_total <= 0:
        raise HTTPException(status_code=400, detail="权重总和必须大于 0")
    if body.stock_rs.tier_b_score > body.stock_rs.tier_a_score:
        raise HTTPException(
            status_code=400,
            detail="stock_rs.tier_b_score 不能大于 stock_rs.tier_a_score",
        )

    try:
        save_editable_config(body.to_payload(), DEFAULT_CONFIG_PATH)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _reload_config()
    return {"status": "ok", "config": get_config()}


@app.post("/api/config/reload")
def reload_config() -> dict[str, str]:
    _reload_config()
    return {"status": "ok"}


@app.post("/api/snapshots/recompute-latest")
def recompute_latest_snapshot(
    snapshot_date: str | None = Query(default=None),
) -> dict[str, Any]:
    date_key = snapshot_date or storage.get_latest_date()
    if not date_key:
        raise HTTPException(status_code=404, detail="尚无快照可重新计算")

    try:
        count = rescore_snapshot(storage, date_key, config)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "status": "ok",
        "snapshot_date": date_key,
        "industry_count": count,
    }


@app.get("/api/snapshots/dates")
def list_dates() -> list[str]:
    return storage.list_snapshot_dates()


@app.get("/api/snapshots/latest")
def latest_snapshot() -> dict[str, Any]:
    latest = storage.get_latest_date()
    if not latest:
        raise HTTPException(status_code=404, detail="尚无快照，请先运行 run_daily.py")
    return get_snapshot(latest)


@app.get("/api/snapshots/{snapshot_date}")
def get_snapshot(snapshot_date: str) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到日期 {snapshot_date} 的快照")

    active = [r for r in rows if not r["excluded"]]
    core_keys = {x.key for x in filter_core_strong_from_rows(active)}
    top_keys = {x.key for x in filter_top_strong_from_rows(active)}
    stock_picks = storage.get_stock_picks_for_snapshot(snapshot_date)

    for row in rows:
        row["is_core"] = row["industry_key"] in core_keys
        row["is_top_strong"] = row["industry_key"] in top_keys
        delta = storage.compare_with_previous(snapshot_date, row["industry_key"])
        row["vs_previous"] = delta
        pick = stock_picks.get(row["industry_key"])
        if pick:
            row["stock_picks"] = pick["tickers"]
            row["stock_screener_url"] = pick.get("screener_url")
            row["stock_picks_error"] = pick.get("error")
        else:
            row["stock_picks"] = []
            row["stock_screener_url"] = None
            row["stock_picks_error"] = None

    rs_count = storage.count_stock_rs(snapshot_date)
    rs_watchlist_count = storage.count_stock_watchlist(snapshot_date)
    rs_watchlist = storage.get_stock_watchlist(snapshot_date, limit=50)
    rs_meta = storage.get_stock_rs_meta(snapshot_date)

    return {
        "snapshot_date": snapshot_date,
        "industry_count": len(rows),
        "core_count": len(core_keys),
        "top_strong_count": len(top_keys),
        "rs_count": rs_count,
        "rs_watchlist_count": rs_watchlist_count,
        "rs_meta": rs_meta,
        "watchlist_preview": rs_watchlist,
        "industries": rows,
    }


def filter_top_strong_from_rows(rows: list[dict[str, Any]]) -> list[Any]:
    """Top N industries by score for the main dashboard."""
    class Item:
        def __init__(self, d: dict[str, Any]):
            self.key = d["industry_key"]
            self.score = float(d.get("score") or 0)
            self.excluded = d.get("excluded", False)

    active = sorted(
        [Item(r) for r in rows if not r.get("excluded")],
        key=lambda x: (-x.score, x.key),
    )
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    return active[:top_n]


def filter_core_strong_from_rows(rows: list[dict[str, Any]]) -> list[Any]:
    """Reuse tag-based core filter for API responses."""
    class Item:
        def __init__(self, d: dict[str, Any]):
            self.key = d["industry_key"]
            self.tags = d.get("tags") or []
            self.excluded = d.get("excluded", False)

    items = [Item(r) for r in rows if not r.get("excluded")]
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    core = [i for i in items if "核心强势" in i.tags]
    return core[:top_n]


@app.post("/api/snapshots/{snapshot_date}/fetch-stocks")
def fetch_snapshot_stocks(
    snapshot_date: str,
    top_only: bool = Query(default=True),
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到日期 {snapshot_date} 的快照")

    active = [r for r in rows if not r["excluded"]]
    if top_only:
        keys = [x.key for x in filter_top_strong_from_rows(active)]
    else:
        keys = [r["industry_key"] for r in active]

    if not keys:
        return {"status": "ok", "snapshot_date": snapshot_date, "fetched": 0, "results": {}}

    results = fetch_and_store_stock_picks(storage, snapshot_date, keys, config)
    return {
        "status": "ok",
        "snapshot_date": snapshot_date,
        "fetched": len(results),
        "results": {
            key: {
                "tickers": value.get("tickers", []),
                "ticker_count": len(value.get("tickers", [])),
                "error": value.get("error"),
            }
            for key, value in results.items()
        },
    }


@app.post("/api/snapshots/{snapshot_date}/compute-rs")
def compute_snapshot_rs(snapshot_date: str) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到日期 {snapshot_date} 的快照")

    class SnapshotIndustry:
        def __init__(self, d: dict[str, Any]):
            self.key = d["industry_key"]
            self.name = d["name"]
            self.score = float(d.get("score") or 0)
            self.excluded = bool(d.get("excluded"))

    scored = sorted(
        [SnapshotIndustry(r) for r in rows if not r.get("excluded")],
        key=lambda x: (-x.score, x.key),
    )
    start_ts = time.time()
    with RS_PROGRESS_LOCK:
        RS_PROGRESS[snapshot_date] = {
            "status": "running",
            "processed": 0,
            "total": 0,
            "started_at": start_ts,
            "updated_at": start_ts,
        }

    def _on_progress(processed: int, total: int) -> None:
        with RS_PROGRESS_LOCK:
            state = RS_PROGRESS.get(snapshot_date)
            if not state:
                return
            state["processed"] = processed
            state["total"] = total
            state["updated_at"] = time.time()

    result = compute_and_store_stock_rs(
        storage,
        snapshot_date,
        scored,
        config,
        progress_callback=_on_progress,
    )
    end_ts = time.time()
    with RS_PROGRESS_LOCK:
        RS_PROGRESS[snapshot_date] = {
            "status": "done",
            "processed": result.get("attempted_count", 0),
            "total": result.get("attempted_count", 0),
            "started_at": start_ts,
            "updated_at": end_ts,
            "elapsed_seconds": round(end_ts - start_ts, 2),
        }
    return {"status": "ok", **result}


@app.get("/api/snapshots/{snapshot_date}/rs-progress")
def rs_progress(snapshot_date: str) -> dict[str, Any]:
    with RS_PROGRESS_LOCK:
        state = dict(RS_PROGRESS.get(snapshot_date) or {})
    if not state:
        return {"snapshot_date": snapshot_date, "status": "idle", "processed": 0, "total": 0}
    total = int(state.get("total") or 0)
    processed = int(state.get("processed") or 0)
    progress_ratio = (processed / total) if total > 0 else 0
    return {
        "snapshot_date": snapshot_date,
        "status": state.get("status", "running"),
        "processed": processed,
        "total": total,
        "progress_ratio": round(progress_ratio, 4),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "elapsed_seconds": state.get("elapsed_seconds"),
    }


@app.get("/api/rs/latest")
def latest_rs(
    limit: int = Query(default=120, ge=1, le=1000),
    watchlist_limit: int = Query(default=120, ge=1, le=1000),
) -> dict[str, Any]:
    latest = storage.get_latest_date()
    if not latest:
        raise HTTPException(status_code=404, detail="尚无快照")
    return rs_snapshot(latest, limit=limit, watchlist_limit=watchlist_limit)


@app.get("/api/rs/{snapshot_date}")
def rs_snapshot(
    snapshot_date: str,
    limit: int = Query(default=120, ge=1, le=1000),
    watchlist_limit: int = Query(default=120, ge=1, le=1000),
) -> dict[str, Any]:
    rs_rows = storage.get_stock_rs(snapshot_date, limit=limit)
    watchlist = storage.get_stock_watchlist(snapshot_date, limit=watchlist_limit)
    if not rs_rows and not watchlist:
        raise HTTPException(status_code=404, detail="该日期尚未生成个股RS数据")
    return {
        "snapshot_date": snapshot_date,
        "rs_count": storage.count_stock_rs(snapshot_date),
        "rs_meta": storage.get_stock_rs_meta(snapshot_date),
        "rows": rs_rows,
        "watchlist": watchlist,
    }


@app.get("/api/industry/{industry_key}/stocks")
def industry_stocks(
    industry_key: str,
    snapshot_date: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    date_key = snapshot_date or storage.get_latest_date()
    if not date_key:
        raise HTTPException(status_code=404, detail="尚无快照")

    if refresh:
        fetch_and_store_stock_picks(storage, date_key, [industry_key], config)

    pick = storage.get_industry_stock_picks(date_key, industry_key)
    if not pick:
        raise HTTPException(status_code=404, detail="该行业尚无股票筛选结果，请先运行 run_daily.py 或点击刷新")

    return {
        "snapshot_date": date_key,
        "industry_key": industry_key,
        "tickers": pick["tickers"],
        "screener_url": pick.get("screener_url"),
        "filters": pick.get("filters"),
        "error": pick.get("error"),
        "fetched_at": pick.get("fetched_at"),
    }


@app.get("/api/industries")
def list_industries(
    snapshot_date: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    date_key = snapshot_date or storage.get_latest_date()
    if not date_key:
        raise HTTPException(status_code=404, detail="尚无快照")
    rows = storage.get_snapshot(date_key)
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in r["name"].lower()]
    return rows


@app.get("/api/industry/{industry_key}/history")
def industry_history(
    industry_key: str,
    metric: str = Query(default="rank_m"),
) -> dict[str, Any]:
    try:
        series = storage.get_industry_history(industry_key, metric)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not series:
        raise HTTPException(status_code=404, detail="无历史数据")

    return {
        "industry_key": industry_key,
        "metric": metric,
        "series": series,
    }


@app.get("/api/industry/{industry_key}/history/multi")
def industry_history_multi(
    industry_key: str,
    metrics: str = Query(default="rank_w,rank_m,rank_q,rank_h,rank_y,score"),
) -> dict[str, Any]:
    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]
    result: dict[str, list[dict[str, Any]]] = {}
    name = None
    for metric in metric_list:
        series = storage.get_industry_history(industry_key, metric)
        if not series:
            continue
        name = series[0].get("name")
        result[metric] = [
            {"date": point["snapshot_date"], "value": point["value"]}
            for point in series
        ]

    if not result:
        raise HTTPException(status_code=404, detail="无历史数据")

    return {
        "industry_key": industry_key,
        "name": name,
        "series": result,
    }


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/strong")
def strong_page() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/breadth")
def breadth_page() -> FileResponse:
    return FileResponse(WEB_DIR / "breadth.html")
