"""Export dashboard JSON bundles for static / GitHub Pages hosting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.breadth_data import DEFAULT_THRESHOLDS, load_breadth_data
from src.config_loader import load_config
from src.logging_config import get_logger
from src.services.auto_scheduler import _stale_days, automation_settings
from src.services.health import _result, check_db
from src.services.snapshots import build_snapshot_response
from src.storage import Storage, latest_trading_date
from src.watchlist_charts import enrich_watchlist_chart_bars

logger = get_logger(__name__)

_RS_ROW_KEEP = (
    "snapshot_date",
    "symbol",
    "rs_score",
    "tier",
    "perf_w",
    "perf_m",
    "perf_q",
    "perf_h",
    "perf_y",
    "rank_w",
    "rank_m",
    "rank_q",
    "rank_h",
    "rank_y",
)

_NEW_STOCK_ROW_KEEP = _RS_ROW_KEEP + (
    "cohort",
    "bar_count",
    "perf_tq",
    "rank_tq",
    "rank_w_delta",
)


def _slim_rs_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in _RS_ROW_KEEP if key in row}


def _slim_new_stock_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in _NEW_STOCK_ROW_KEEP if key in row}


def _breadth_config_payload(config: dict[str, Any], storage: Storage) -> dict[str, Any]:
    breadth_cfg = dict(DEFAULT_THRESHOLDS)
    breadth_cfg.update(storage.get_breadth_threshold_overrides())
    confluence = config.get("breadth_confluence") or {}
    min_score = int(confluence.get("min_score", 2))
    return {
        "thresholds": breadth_cfg,
        "breadth_confluence": {"min_score": min_score},
    }


EXPORT_FILES = (
    "meta.json",
    "snapshot.json",
    "rs.json",
    "rs_watchlist.json",
    "automation.json",
    "breadth.json",
    "breadth_config.json",
    "health.json",
    "sync_progress.json",
)


def build_export_automation_status(storage: Storage, config: dict[str, Any]) -> dict[str, Any]:
    cfg = automation_settings(config)
    trade_date = latest_trading_date()
    display_date = storage.get_latest_date()
    lag_days = _stale_days(display_date, trade_date) if display_date else 0
    run = storage.get_snapshot_run(trade_date) if trade_date else None
    validation = ((run or {}).get("details") or {}).get("validation") if run else None
    if display_date:
        if isinstance(validation, dict):
            daily_status = str(validation.get("overall") or "ready")
            headline = validation.get("headline") or f"As of {display_date}"
        else:
            daily_status = "ready"
            headline = f"As of {display_date}"
    else:
        daily_status = "idle"
        headline = f"No data for {trade_date} yet"
    if lag_days > 0 and display_date:
        headline = f"As of {display_date} · target {trade_date} ({lag_days}d behind)"
    return {
        "enabled": False,
        "source": "static_export",
        "timezone": cfg["timezone"],
        "schedule": f"{cfg['daily_hour']:02d}:{cfg['daily_minute']:02d}",
        "weekdays_only": cfg["weekdays_only"],
        "trade_date": trade_date,
        "target_date": trade_date,
        "display_date": display_date,
        "lag_days": lag_days,
        "has_snapshot": bool(display_date),
        "daily_status": daily_status,
        "headline": headline,
        "running": False,
    }


def build_export_health(storage: Storage, config: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {"db": check_db(storage)}
    latest = storage.get_latest_date()
    checks["snapshot"] = _result(
        bool(latest),
        0,
        detail=latest or "no snapshot",
    )
    breadth_rows = storage.get_breadth_daily(limit=1)
    checks["breadth"] = _result(bool(breadth_rows), 0, detail=f"{len(breadth_rows)} row(s) cached")
    rs_date = latest
    rs_count = storage.count_stock_rs(rs_date) if rs_date else 0
    checks["stock_rs"] = _result(rs_count > 0, 0, detail=f"{rs_count} symbols" if rs_date else "no rs")
    ok_count = sum(1 for v in checks.values() if v.get("ok"))
    if ok_count == len(checks):
        status = "ok"
    elif checks["db"].get("ok"):
        status = "degraded"
    else:
        status = "error"
    return {
        "status": status,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


def build_public_dashboard_payloads(
    storage: Storage,
    config: dict[str, Any],
    *,
    rs_limit: int = 500,
    watchlist_limit: int = 120,
    breadth_limit: int = 756,
) -> dict[str, Any]:
    exported_at = datetime.now(timezone.utc).isoformat()
    latest = storage.get_latest_date()
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))

    if latest:
        rows = storage.get_snapshot(latest)
        snapshot = build_snapshot_response(
            storage=storage,
            snapshot_date=latest,
            rows=rows,
            top_n=top_n,
        )
        watchlist = enrich_watchlist_chart_bars(
            storage.get_stock_watchlist(latest, limit=watchlist_limit),
        )
        rs_rows = [_slim_rs_row(row) for row in storage.get_stock_rs(latest, limit=max(rs_limit, 1))]
        new_stock_rows = [_slim_new_stock_row(row) for row in storage.get_stock_rs_new(latest, limit=500)]
        new_stock_leaderboard = [
            _slim_new_stock_row(row)
            for row in storage.get_stock_rs_new(latest, leaderboard_only=True, limit=500)
        ]
        rs_payload = {
            "snapshot_date": latest,
            "rs_count": storage.count_stock_rs(latest),
            "rs_meta": storage.get_stock_rs_meta(latest),
            "rows": rs_rows,
            "new_stock_rows": new_stock_rows,
            "new_stock_leaderboard": new_stock_leaderboard,
            "watchlist": watchlist,
        }
        rs_watchlist = {
            "snapshot_date": latest,
            "rs_count": rs_payload["rs_count"],
            "rs_meta": rs_payload["rs_meta"],
            "rows": [],
            "new_stock_rows": [],
            "new_stock_leaderboard": [],
            "watchlist": watchlist,
        }
    else:
        snapshot = {
            "snapshot_date": None,
            "industries": [],
            "top_strong_count": top_n,
        }
        rs_payload = {
            "snapshot_date": None,
            "rs_count": 0,
            "rs_meta": {},
            "rows": [],
            "new_stock_rows": [],
            "new_stock_leaderboard": [],
            "watchlist": [],
        }
        rs_watchlist = rs_payload

    try:
        breadth = load_breadth_data(
            storage,
            force_refresh=False,
            limit=breadth_limit,
            config=config,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("public export breadth load failed: %s", exc)
        breadth = {
            "error": str(exc),
            "rows": [],
            "latest_date": None,
        }

    meta = {
        "exported_at": exported_at,
        "snapshot_date": latest,
        "readonly": True,
        "source": "github-pages",
    }

    return {
        "meta.json": meta,
        "snapshot.json": snapshot,
        "rs.json": rs_payload,
        "rs_watchlist.json": rs_watchlist,
        "automation.json": build_export_automation_status(storage, config),
        "breadth.json": breadth,
        "breadth_config.json": _breadth_config_payload(config, storage),
        "health.json": build_export_health(storage, config),
        "sync_progress.json": {
            "kind": "breadth",
            "status": "done",
            "message": f"Read-only snapshot · {exported_at}",
            "running": False,
        },
    }


def write_public_dashboard(out_dir: Path, payloads: dict[str, Any]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in EXPORT_FILES:
        path = out_dir / name
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payloads[name], fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        written.append(path)
    return written


def export_public_dashboard(
    out_dir: Path,
    *,
    db_path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_config()
    storage = Storage(db_path or Path(cfg.get("database", {}).get("path", "data/industry_strength.db")))
    payloads = build_public_dashboard_payloads(storage, cfg)
    write_public_dashboard(out_dir, payloads)
    return payloads["meta.json"]
