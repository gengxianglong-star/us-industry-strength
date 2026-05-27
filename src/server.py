"""FastAPI server for industry strength dashboard."""

from __future__ import annotations

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
from src.breadth_data import (
    DEFAULT_THRESHOLDS,
    load_breadth_data,
    validate_breadth_thresholds,
)
from src.rescore import rescore_snapshot
from src.services.snapshots import (
    build_snapshot_response,
    scored_industries_from_rows,
    top_strong_from_rows,
)
from src.stock_rs import rebuild_stock_watchlist_for_snapshot
from src.stock_picks import fetch_and_store_stock_picks
from src.services.breadth_jobs import BreadthSyncService
from src.services.rs_jobs import RsJobService
from src.storage import Storage

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="US Industry Strength")
config = load_config()
storage = Storage(db_path(config))


@app.on_event("startup")
def _ensure_database_schema() -> None:
    storage._init_db()


RS_JOB_SERVICE = RsJobService()
BREADTH_SYNC_SERVICE = BreadthSyncService()


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
    limit: int = Query(default=180, ge=10, le=10000),
) -> dict[str, Any]:
    return load_breadth_data(storage, force_refresh=refresh, limit=limit, config=config)


@app.post("/api/breadth/sync")
def sync_breadth(
    full: bool = Query(default=False),
    async_mode: bool = Query(default=True),
) -> dict[str, Any]:
    try:
        return BREADTH_SYNC_SERVICE.start_sync(storage, full=full, async_mode=async_mode)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/breadth/ping")
def breadth_ping() -> dict[str, Any]:
    """Instant check: server up + proxy config (no Google download)."""
    from src.breadth_data import _breadth_settings

    settings = _breadth_settings(config)
    return {
        "status": "ok",
        "proxy_url": settings.get("proxy_url") or "",
        "proxy_source": settings.get("proxy_source") or "none",
        "curl_only": settings.get("curl_only"),
        "prefer_curl": settings.get("prefer_curl"),
    }


@app.get("/api/breadth/fetch-test")
def breadth_fetch_test(quick: bool = Query(default=False)) -> dict[str, Any]:
    """Test Google Sheet download (curl + system proxy). ?quick=true skips download."""
    from src.breadth_data import (
        PRIMARY_MARKET_MONITOR_GID,
        _breadth_settings,
        _fetch_gid_rows_remote,
    )

    settings = _breadth_settings(config)
    if quick:
        return {
            "ok": True,
            "quick": True,
            "message": "服务正常；未下载 Google Sheet。去掉 ?quick=true 可测完整拉取。",
            "proxy_url": settings.get("proxy_url") or "",
            "proxy_source": settings.get("proxy_source") or "none",
            "curl_only": settings.get("curl_only"),
        }
    try:
        _, _, data_rows = _fetch_gid_rows_remote(PRIMARY_MARKET_MONITOR_GID, settings)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "row_count": len(data_rows),
        "proxy_url": settings.get("proxy_url") or "",
        "proxy_source": settings.get("proxy_source") or "none",
        "curl_only": settings.get("curl_only"),
    }


@app.get("/api/breadth/sync-progress")
def breadth_sync_progress() -> dict[str, Any]:
    state = BREADTH_SYNC_SERVICE.get_progress_state(storage)
    processed = int(state.get("processed") or 0)
    total = int(state.get("total") or 0)
    progress_ratio = round((processed / total), 4) if total > 0 else 0.0
    state["progress_ratio"] = progress_ratio
    return state


@app.get("/api/breadth/config")
def get_breadth_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_THRESHOLDS)
    cfg.update(storage.get_breadth_threshold_overrides())
    return {"thresholds": cfg}


@app.put("/api/breadth/config")
def update_breadth_config(body: dict[str, Any]) -> dict[str, Any]:
    payload = body.get("thresholds") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="thresholds payload required")
    allowed = set(DEFAULT_THRESHOLDS.keys())
    sanitized = {k: float(v) for k, v in payload.items() if k in allowed}
    if not sanitized:
        raise HTTPException(status_code=400, detail="no valid breadth threshold keys")
    merged = dict(DEFAULT_THRESHOLDS)
    merged.update(storage.get_breadth_threshold_overrides())
    merged.update(sanitized)
    try:
        validate_breadth_thresholds(merged)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    storage.save_breadth_threshold_overrides(sanitized)
    cfg = dict(DEFAULT_THRESHOLDS)
    cfg.update(storage.get_breadth_threshold_overrides())
    return {"status": "ok", "thresholds": cfg}


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
    if body.stock_rs.tier_b_score is not None and body.stock_rs.tier_a_score is not None:
        if body.stock_rs.tier_b_score > body.stock_rs.tier_a_score:
            raise HTTPException(
                status_code=400,
                detail="stock_rs.tier_b_score 不能大于 stock_rs.tier_a_score",
            )
    elif body.stock_rs.tier_b_score is not None or body.stock_rs.tier_a_score is not None:
        current_rs = config.get("stock_rs", {})
        tier_a = float(
            body.stock_rs.tier_a_score
            if body.stock_rs.tier_a_score is not None
            else current_rs.get("tier_a_score", 0.8)
        )
        tier_b = float(
            body.stock_rs.tier_b_score
            if body.stock_rs.tier_b_score is not None
            else current_rs.get("tier_b_score", 0.65)
        )
        if tier_b > tier_a:
            raise HTTPException(
                status_code=400,
                detail="stock_rs.tier_b_score 不能大于 stock_rs.tier_a_score",
            )

    try:
        save_editable_config(body.to_payload(), DEFAULT_CONFIG_PATH, base_config=config)
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
        result = rescore_snapshot(storage, date_key, config, rebuild_watchlist=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "status": "ok",
        "snapshot_date": date_key,
        "industry_count": result["industry_count"],
        "watchlist_rebuilt": result.get("watchlist_count") is not None,
        "watchlist_count": result.get("watchlist_count"),
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
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    return build_snapshot_response(
        storage=storage,
        snapshot_date=snapshot_date,
        rows=rows,
        top_n=top_n,
    )


@app.get("/api/snapshots/{snapshot_date}/run-status")
def snapshot_run_status(snapshot_date: str) -> dict[str, Any]:
    status = storage.get_snapshot_run(snapshot_date)
    if not status:
        if storage.get_snapshot(snapshot_date):
            return {
                "snapshot_date": snapshot_date,
                "status": "completed",
                "current_step": "legacy_snapshot",
                "started_at": None,
                "updated_at": None,
                "finished_at": None,
                "error": None,
                "details": {},
            }
        raise HTTPException(status_code=404, detail=f"未找到日期 {snapshot_date} 的运行状态")
    return status


@app.post("/api/snapshots/{snapshot_date}/fetch-stocks")
def fetch_snapshot_stocks(
    snapshot_date: str,
    top_only: bool = Query(default=True),
    refresh_watchlist: bool = Query(default=True),
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到日期 {snapshot_date} 的快照")

    active = [r for r in rows if not r["excluded"]]
    if top_only:
        top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
        keys = [x.key for x in top_strong_from_rows(active, top_n=top_n)]
    else:
        keys = [r["industry_key"] for r in active]

    if not keys:
        return {"status": "ok", "snapshot_date": snapshot_date, "fetched": 0, "results": {}}

    results = fetch_and_store_stock_picks(storage, snapshot_date, keys, config)
    watchlist_info: dict[str, Any] | None = None
    if refresh_watchlist:
        watchlist_info = rebuild_stock_watchlist_for_snapshot(
            storage,
            snapshot_date,
            scored_industries_from_rows(rows),
            config,
        )
    return {
        "status": "ok",
        "snapshot_date": snapshot_date,
        "fetched": len(results),
        "watchlist": watchlist_info,
        "results": {
            key: {
                "tickers": value.get("tickers", []),
                "ticker_count": len(value.get("tickers", [])),
                "error": value.get("error"),
                "screener_url": value.get("screener_url"),
                "filters": value.get("filters"),
            }
            for key, value in results.items()
        },
    }


@app.post("/api/snapshots/{snapshot_date}/compute-rs")
def compute_snapshot_rs(
    snapshot_date: str,
    async_mode: bool = Query(default=True),
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到日期 {snapshot_date} 的快照")
    scored = scored_industries_from_rows(rows)
    try:
        return RS_JOB_SERVICE.start_compute_rs(
            storage=storage,
            snapshot_date=snapshot_date,
            scored=scored,
            config=config,
            async_mode=async_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/snapshots/{snapshot_date}/compute-new-stock-rs")
def compute_snapshot_new_stock_rs(
    snapshot_date: str,
    async_mode: bool = Query(default=False),
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"未找到日期 {snapshot_date} 的快照")
    if not storage.get_stock_rs_raw(snapshot_date):
        raise HTTPException(status_code=400, detail="请先完成主 RS 计算（刷新个股RS）")
    try:
        return RS_JOB_SERVICE.start_compute_new_rs(
            storage=storage,
            snapshot_date=snapshot_date,
            config=config,
            async_mode=async_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/snapshots/{snapshot_date}/rs-progress")
def rs_progress(
    snapshot_date: str,
    kind: str = Query(default="main", pattern="^(main|new)$"),
) -> dict[str, Any]:
    return RS_JOB_SERVICE.get_progress(snapshot_date, storage=storage, job_kind=kind)


@app.post("/api/snapshots/{snapshot_date}/rs-cancel")
def rs_cancel(
    snapshot_date: str,
    kind: str = Query(default="main", pattern="^(main|new)$"),
) -> dict[str, Any]:
    return RS_JOB_SERVICE.request_cancel(snapshot_date, storage=storage, job_kind=kind)


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
        "new_stock_rows": storage.get_stock_rs_new(snapshot_date, limit=500),
        "new_stock_leaderboard": storage.get_stock_rs_new(
            snapshot_date,
            leaderboard_only=True,
            limit=500,
        ),
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


@app.get("/breadth/network-test")
def breadth_network_test_page() -> FileResponse:
    return FileResponse(WEB_DIR / "breadth_network_test.html")
