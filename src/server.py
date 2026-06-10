"""FastAPI server for industry strength dashboard."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from src.auth import require_api_key

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
from src.errors import ApiError
from src.rescore import rescore_snapshot
from src.services.health import build_health_report
from src.services.snapshots import (
    build_snapshot_response,
    scored_industries_from_rows,
    top_strong_from_rows,
)
from src.stock_rs import rebuild_stock_watchlist_for_snapshot
from src.watchlist_charts import attach_watchlist_chart_bars
from src.stock_picks import fetch_and_store_stock_picks
from src.services.auto_scheduler import AutoScheduler
from src.services.breadth_jobs import BreadthSyncService
from src.services.daily_jobs import (
    DailyJobService,
    finalize_snapshot_run,
    snapshots_needing_finalize_after_rs,
)
from src.services.rs_jobs import RsJobService
from src.logging_config import get_logger
from src.storage import Storage, today_snapshot_date

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
WEB_DIST = WEB_DIR / "dist"
SPA_INDEX = WEB_DIST / "index.html"
USE_SPA = SPA_INDEX.is_file()

@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    """Startup / shutdown lifecycle (replaces deprecated on_event)."""
    # ── startup ──
    storage._init_db()
    recovered = storage.recover_stale_jobs(stale_seconds=1800)
    finalize_dates = list(dict.fromkeys(
        [*recovered.get("finalize", []), *snapshots_needing_finalize_after_rs(storage)]
    ))
    for snap_date in finalize_dates:
        try:
            finalize_snapshot_run(storage, config, snap_date)
            logger.info(
                "startup finalized snapshot run after RS: %s", snap_date,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "startup finalize failed for %s: %s", snap_date, exc,
            )
    if recovered["snapshot_runs"] or recovered["rs_jobs"]:
        logger.info("startup recovered stale jobs: %s", recovered)
    AUTO_SCHEDULER.start()
    if recovered["snapshot_runs"] or recovered["rs_jobs"] or recovered.get("finalize"):
        AUTO_SCHEDULER.schedule_recovery(reason="stale_recovered")
    yield
    # ── shutdown ──
    AUTO_SCHEDULER.stop()


app = FastAPI(title="US Industry Strength", lifespan=_app_lifespan)
config = load_config()
storage = Storage(db_path(config))

# Sync to app.state so auth dependency can read config.
app.state.config = config
app.state.storage = storage

RS_JOB_SERVICE = RsJobService()
BREADTH_SYNC_SERVICE = BreadthSyncService()
DAILY_JOB_SERVICE = DailyJobService()
AUTO_SCHEDULER = AutoScheduler(
    storage=storage,
    config_getter=lambda: config,
    daily_service=DAILY_JOB_SERVICE,
    rs_service=RS_JOB_SERVICE,
    breadth_service=BREADTH_SYNC_SERVICE,
)


@app.exception_handler(ApiError)
def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(HTTPException)
def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        payload = dict(detail)
        payload.setdefault("code", "HTTP_ERROR")
        payload.setdefault("message", str(payload.get("detail") or exc.status_code))
        payload.setdefault("hint", "")
        payload.setdefault("retryable", exc.status_code >= 500)
    else:
        payload = {
            "code": "HTTP_ERROR",
            "message": str(detail or exc.status_code),
            "hint": "",
            "retryable": exc.status_code >= 500,
        }
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(Exception)
def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "hint": "Retry shortly; check server logs if it persists.",
            "retryable": True,
            "detail": str(exc),
        },
    )


def _reload_config() -> None:
    global config, storage
    # 先保留旧管理员的引用
    old_storage = storage

    config = load_config()
    storage = Storage(db_path(config))
    app.state.config = config
    app.state.storage = storage
    AUTO_SCHEDULER.update_storage(storage)

    # 优雅地关闭旧的数据库连接，释放资源
    if old_storage:
        old_storage.close()


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


@app.get("/api/health")
def api_health(quick: bool = Query(default=False)) -> dict[str, Any]:
    return build_health_report(storage, config, quick=quick)


@app.post("/api/daily/run", dependencies=[Depends(require_api_key)])
def daily_run(
    snapshot_date: str | None = Query(default=None),
    force: bool = Query(default=False),
    async_mode: bool = Query(default=True),
) -> dict[str, Any]:
    try:
        return DAILY_JOB_SERVICE.start_run(
            storage,
            config,
            snapshot_date,
            force=force,
            async_mode=async_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/daily/status")
def daily_status(snapshot_date: str | None = Query(default=None)) -> dict[str, Any]:
    return DAILY_JOB_SERVICE.get_status(storage, config, snapshot_date)


@app.get("/api/dashboard/today")
def dashboard_today(snapshot_date: str | None = Query(default=None)) -> dict[str, Any]:
    return DAILY_JOB_SERVICE.build_dashboard(storage, config, snapshot_date)


@app.get("/api/automation/status")
def automation_status() -> dict[str, Any]:
    return AUTO_SCHEDULER.status()


@app.post("/api/automation/ensure", dependencies=[Depends(require_api_key)])
def automation_ensure() -> dict[str, Any]:
    """Browser-open hook: start catch-up / retry failed jobs without manual CLI."""
    return AUTO_SCHEDULER.ensure_now(reason="browser")


@app.get("/api/breadth")
def get_breadth_data(
    refresh: bool = Query(default=False),
    limit: int = Query(default=180, ge=10, le=10000),
) -> dict[str, Any]:
    if refresh:
        BREADTH_SYNC_SERVICE.start_sync(storage, full=False, async_mode=True)
    try:
        return load_breadth_data(storage, limit=limit, config=config)
    except ValueError as exc:
        if "empty" in str(exc).lower():
            sync = BREADTH_SYNC_SERVICE.start_sync(storage, full=True, async_mode=True)
            return {
                "rows": [],
                "limit": limit,
                "syncing": True,
                "sync_status": sync.get("status"),
                "message": str(exc),
            }
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/breadth/sync", dependencies=[Depends(require_api_key)])
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
            "message": "OK — Google Sheet not fetched. Drop ?quick=true for full pull test.",
            "proxy_url": settings.get("proxy_url") or "",
            "proxy_source": settings.get("proxy_source") or "none",
            "curl_only": settings.get("curl_only"),
        }
    try:
        _, _, data_rows = _fetch_gid_rows_remote(PRIMARY_MARKET_MONITOR_GID, settings)
    except Exception as exc:  # noqa: BLE001
        logger.exception("breadth fetch-test failed")
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
    state.setdefault("kind", "breadth")
    return state


@app.get("/api/breadth/config")
def get_breadth_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_THRESHOLDS)
    cfg.update(storage.get_breadth_threshold_overrides())
    confluence = config.get("breadth_confluence") or {}
    min_score = int(confluence.get("min_score", 2))
    return {
        "thresholds": cfg,
        "breadth_confluence": {"min_score": min_score},
    }


@app.put("/api/breadth/config", dependencies=[Depends(require_api_key)])
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


@app.put("/api/config", dependencies=[Depends(require_api_key)])
def update_config(body: ConfigUpdate) -> dict[str, Any]:
    if body.thresholds.tier_b_score > body.thresholds.tier_a_score:
        raise HTTPException(
            status_code=400,
            detail="tier_b_score cannot exceed tier_a_score",
        )

    weight_total = sum(
        getattr(body.weights, field) for field in body.weights.model_fields
    )
    if weight_total <= 0:
        raise HTTPException(status_code=400, detail="Weight sum must be greater than 0")
    if body.stock_rs.tier_b_score is not None and body.stock_rs.tier_a_score is not None:
        if body.stock_rs.tier_b_score > body.stock_rs.tier_a_score:
            raise HTTPException(
                status_code=400,
                detail="stock_rs.tier_b_score cannot exceed tier_a_score",
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
                detail="stock_rs.tier_b_score cannot exceed tier_a_score",
            )

    try:
        save_editable_config(body.to_payload(), DEFAULT_CONFIG_PATH, base_config=config)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _reload_config()
    return {"status": "ok", "config": get_config()}


@app.post("/api/config/reload", dependencies=[Depends(require_api_key)])
def reload_config() -> dict[str, str]:
    _reload_config()
    return {"status": "ok"}


# ── AI Brief ──────────────────────────────────────────────────────────

@app.post("/api/ai/brief")
async def ai_brief() -> dict[str, Any]:
    """Generate a daily market briefing via Gemini AI."""
    from src.services.ai_brief import generate_ai_brief, is_available

    if not is_available():
        raise HTTPException(
            status_code=501,
            detail="Gemini API 未配置。请在 .env 文件中设置 GEMINI_API_KEY。",
        )

    # 将所有同步的数据库查询放入线程池（辅路），防止阻塞 FastAPI 的核心事件循环
    latest = await run_in_threadpool(storage.get_latest_date)
    if not latest:
        raise HTTPException(status_code=404, detail="No snapshot yet — run daily first")

    rows = await run_in_threadpool(storage.get_snapshot, latest)
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    from dataclasses import asdict
    from src.services.snapshots import top_strong_from_rows

    top = top_strong_from_rows(rows, top_n=top_n)
    watchlist = await run_in_threadpool(storage.get_stock_watchlist, latest)

    breadth_latest = None
    try:
        from src.breadth_data import load_breadth_data

        # 同样放入线程池执行
        breadth_payload = await run_in_threadpool(
            load_breadth_data, storage, force_refresh=False, limit=1, config=config
        )
        rows_b = breadth_payload.get("rows") or []
        breadth_latest = rows_b[0] if rows_b else None
    except Exception:
        logger.debug("breadth data not available for AI brief", exc_info=True)

    try:
        result = await generate_ai_brief(
            snapshot_date=latest,
            industry_count=len(rows),
            top_industries=[asdict(s) for s in top],
            watchlist=watchlist,
            breadth_latest=breadth_latest,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return result


# ── Snapshots ─────────────────────────────────────────────────────────
def recompute_latest_snapshot(
    snapshot_date: str | None = Query(default=None),
) -> dict[str, Any]:
    date_key = snapshot_date or storage.get_latest_date()
    if not date_key:
        raise HTTPException(status_code=404, detail="No snapshot to rescore")

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
        raise HTTPException(status_code=404, detail="No snapshot yet — run daily first")
    return get_snapshot(latest)


@app.get("/api/snapshots/{snapshot_date}")
def get_snapshot(snapshot_date: str) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No snapshot for {snapshot_date}")
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
        raise HTTPException(status_code=404, detail=f"No run status for {snapshot_date}")
    return status


@app.post("/api/snapshots/{snapshot_date}/fetch-stocks", dependencies=[Depends(require_api_key)])
def fetch_snapshot_stocks(
    snapshot_date: str,
    top_only: bool = Query(default=True),
    refresh_watchlist: bool = Query(default=True),
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No snapshot for {snapshot_date}")

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


@app.post("/api/snapshots/{snapshot_date}/compute-rs", dependencies=[Depends(require_api_key)])
def compute_snapshot_rs(
    snapshot_date: str,
    async_mode: bool = Query(default=True),
    force_full: bool = Query(default=False),
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No snapshot for {snapshot_date}")
    scored = scored_industries_from_rows(rows)
    try:
        return RS_JOB_SERVICE.start_compute_rs(
            storage=storage,
            snapshot_date=snapshot_date,
            scored=scored,
            config=config,
            force_full=force_full,
            async_mode=async_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/snapshots/{snapshot_date}/compute-new-stock-rs", dependencies=[Depends(require_api_key)])
def compute_snapshot_new_stock_rs(
    snapshot_date: str,
    async_mode: bool = Query(default=False),
) -> dict[str, Any]:
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No snapshot for {snapshot_date}")
    if not storage.get_stock_rs_raw(snapshot_date):
        raise HTTPException(status_code=400, detail="Run main RS first")
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


@app.post("/api/snapshots/{snapshot_date}/rs-cancel", dependencies=[Depends(require_api_key)])
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
        raise HTTPException(status_code=404, detail="No snapshot")
    return rs_snapshot(latest, limit=limit, watchlist_limit=watchlist_limit)


@app.get("/api/rs/{snapshot_date}")
def rs_snapshot(
    snapshot_date: str,
    limit: int = Query(default=120, ge=0, le=1000),
    watchlist_limit: int = Query(default=120, ge=1, le=1000),
    watchlist_only: bool = Query(default=False),
) -> dict[str, Any]:
    watchlist = storage.get_stock_watchlist(snapshot_date, limit=watchlist_limit)
    if watchlist_only:
        watchlist = attach_watchlist_chart_bars(watchlist)
        return {
            "snapshot_date": snapshot_date,
            "rs_count": storage.count_stock_rs(snapshot_date),
            "rs_meta": storage.get_stock_rs_meta(snapshot_date),
            "rows": [],
            "new_stock_rows": [],
            "new_stock_leaderboard": [],
            "watchlist": watchlist,
        }
    rs_rows = storage.get_stock_rs(snapshot_date, limit=max(limit, 1))
    if not rs_rows and not watchlist:
        raise HTTPException(status_code=404, detail=f"No stock RS for {snapshot_date}")
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
        raise HTTPException(status_code=404, detail="No snapshot")

    if refresh:
        fetch_and_store_stock_picks(storage, date_key, [industry_key], config)

    pick = storage.get_industry_stock_picks(date_key, industry_key)
    if not pick:
        raise HTTPException(status_code=404, detail="No stock screen for this industry — run daily first")

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
        raise HTTPException(status_code=404, detail="No snapshot")
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
        raise HTTPException(status_code=404, detail="No history")

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
        raise HTTPException(status_code=404, detail="No history")

    return {
        "industry_key": industry_key,
        "name": name,
        "series": result,
    }


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
if USE_SPA:
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="spa_assets")
    spa_data = WEB_DIST / "data"
    if spa_data.is_dir():
        app.mount("/data", StaticFiles(directory=spa_data), name="spa_data")


def _spa_index() -> FileResponse:
    return FileResponse(SPA_INDEX)


@app.get("/")
def index() -> FileResponse:
    if USE_SPA:
        return _spa_index()
    return FileResponse(WEB_DIR / "index.html")


@app.get("/strong")
def strong_page() -> FileResponse:
    if USE_SPA:
        return _spa_index()
    return FileResponse(WEB_DIR / "index.html")


@app.get("/breadth")
def breadth_page() -> FileResponse:
    if USE_SPA:
        return _spa_index()
    return FileResponse(WEB_DIR / "index.html")


@app.get("/terminal")
def quant_terminal_page() -> FileResponse:
    if USE_SPA:
        return _spa_index()
    return FileResponse(WEB_DIR / "index.html")


@app.get("/breadth/network-test")
def breadth_network_test_page() -> FileResponse:
    return FileResponse(WEB_DIR / "breadth_network_test.html")
