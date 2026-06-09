"""System health checks for diagnostics."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from src.breadth_data import PRIMARY_MARKET_MONITOR_GID, _breadth_settings, _fetch_gid_rows_remote
from src.logging_config import get_logger
from src.storage import Storage

logger = get_logger(__name__)


def _result(ok: bool, latency_ms: int, detail: str = "", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": ok, "latency_ms": latency_ms, "detail": detail}
    payload.update(extra)
    return payload


def check_db(storage: Storage) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with storage._connect() as conn:  # noqa: SLF001
            conn.execute("SELECT 1").fetchone()
        return _result(True, int((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001
        logger.debug("health check failed: %s", exc)
        return _result(False, int((time.perf_counter() - started) * 1000), detail=str(exc))


def check_proxy(config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    settings = _breadth_settings(config)
    proxy_url = settings.get("proxy_url") or ""
    proxy_source = settings.get("proxy_source") or "none"
    ok = proxy_source != "none"
    detail = "" if ok else "No proxy detected — Google access may fail on restricted networks"
    return _result(
        ok,
        int((time.perf_counter() - started) * 1000),
        detail=detail,
        proxy_url=proxy_url,
        proxy_source=proxy_source,
    )


def check_finviz(config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from src.finviz_scraper import fetch_industries_health_check

        ok, detail = fetch_industries_health_check(config)
        return _result(
            ok,
            int((time.perf_counter() - started) * 1000),
            detail=detail or None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("health check failed: %s", exc)
        return _result(False, int((time.perf_counter() - started) * 1000), detail=str(exc))


def check_breadth_source(config: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        _, _, rows = _fetch_gid_rows_remote(PRIMARY_MARKET_MONITOR_GID, _breadth_settings(config))
        return _result(True, int((time.perf_counter() - started) * 1000), row_count=len(rows))
    except Exception as exc:  # noqa: BLE001
        logger.debug("health check failed: %s", exc)
        return _result(False, int((time.perf_counter() - started) * 1000), detail=str(exc))


def build_health_report(
    storage: Storage,
    config: dict[str, Any],
    *,
    quick: bool = False,
) -> dict[str, Any]:
    checks = {
        "db": check_db(storage),
        "proxy": check_proxy(config),
    }
    if not quick:
        checks["finviz"] = check_finviz(config)
        checks["breadth_source"] = check_breadth_source(config)
    if all(v.get("ok") for v in checks.values()):
        status = "ok"
    elif checks["db"].get("ok") and (
        quick or checks.get("finviz", {}).get("ok") or checks.get("breadth_source", {}).get("ok")
    ):
        status = "degraded"
    else:
        status = "error"
    return {
        "status": status,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
