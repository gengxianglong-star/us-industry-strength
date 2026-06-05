"""Daily pipeline step validation and aggregate dashboard status."""

from __future__ import annotations

from typing import Any

from src.storage import Storage


def _level(status: str) -> str:
    if status == "failed":
        return "red"
    if status == "degraded":
        return "yellow"
    return "green"


def validate_industry_step(
    *,
    industry_count: int,
    top_count: int,
    top_expected: int,
) -> dict[str, Any]:
    if industry_count >= 130 and top_count >= top_expected:
        status = "done"
    elif industry_count >= 120 and top_count >= max(5, top_expected - 5):
        status = "degraded"
    else:
        status = "failed"
    return {
        "step": "industry",
        "status": status,
        "level": _level(status if status != "done" else "done"),
        "industry_count": industry_count,
        "top_count": top_count,
        "top_expected": top_expected,
    }


def validate_picks_step(
    *,
    pick_total: int,
    pick_errors: int,
    pick_stale: int,
    industries_with_tickers: int,
) -> dict[str, Any]:
    ok = max(0, pick_total - pick_errors)
    if pick_total == 0:
        status = "skipped"
    elif pick_errors == 0:
        status = "done"
    elif pick_errors <= 4 and industries_with_tickers >= 8:
        status = "degraded"
    elif pick_errors >= 5 or industries_with_tickers < 5:
        status = "failed"
    else:
        status = "degraded"
    return {
        "step": "picks",
        "status": status,
        "level": _level(status if status not in {"done", "skipped"} else "done"),
        "ok": ok,
        "errors": pick_errors,
        "stale": pick_stale,
        "industries_with_tickers": industries_with_tickers,
    }


def validate_rs_main_step(
    *,
    computed_count: int,
    universe_count: int,
    coverage_ratio: float,
    no_bars_count: int,
) -> dict[str, Any]:
    no_bars_ratio = (no_bars_count / universe_count) if universe_count else 1.0
    if no_bars_ratio >= 0.20:
        status = "failed" if computed_count < 500 else "degraded"
    elif no_bars_ratio >= 0.08:
        status = "degraded" if computed_count >= 200 else "failed"
    elif computed_count >= 500 and coverage_ratio >= 0.05 and no_bars_ratio < 0.95:
        status = "done"
    elif computed_count >= 200 and coverage_ratio >= 0.02:
        status = "degraded"
    else:
        status = "failed"
    return {
        "step": "rs_main",
        "status": status,
        "level": _level(status if status != "done" else "done"),
        "computed_count": computed_count,
        "universe_count": universe_count,
        "coverage_ratio": round(float(coverage_ratio), 4),
        "no_bars_count": no_bars_count,
        "no_bars_ratio": round(float(no_bars_ratio), 4),
    }


def validate_rs_new_step(
    *,
    enabled: bool,
    leaderboard_count: int,
    error: str | None = None,
) -> dict[str, Any]:
    if not enabled:
        return {"step": "rs_new", "status": "skipped", "level": "green", "leaderboard_count": 0}
    if error:
        return {
            "step": "rs_new",
            "status": "degraded",
            "level": "yellow",
            "leaderboard_count": leaderboard_count,
            "error": error,
        }
    return {
        "step": "rs_new",
        "status": "done",
        "level": "green",
        "leaderboard_count": leaderboard_count,
    }


def validate_watchlist_step(
    *,
    watchlist_count: int,
    picks_status: str,
    rs_status: str,
    pick_stale: int,
    pick_total: int,
) -> dict[str, Any]:
    if rs_status == "failed" or picks_status == "failed":
        status = "failed"
    elif rs_status == "running":
        status = "degraded"
    elif watchlist_count >= 3 and pick_stale < pick_total:
        status = "done"
    elif watchlist_count == 0 and picks_status in {"degraded", "done"} and rs_status in {"degraded", "done"}:
        status = "degraded"
    elif watchlist_count > 0:
        status = "degraded" if watchlist_count < 3 else "done"
    else:
        status = "degraded"
    return {
        "step": "watchlist",
        "status": status,
        "level": _level(status if status != "done" else "done"),
        "count": watchlist_count,
    }


def validate_breadth_step(
    *,
    merged_row_count: int,
    latest_trade_date: str | None,
    target_date: str,
    stale_days: int,
    skipped: bool,
) -> dict[str, Any]:
    if skipped:
        return {"step": "breadth", "status": "skipped", "level": "green", "latest_date": latest_trade_date}
    if merged_row_count <= 0:
        return {
            "step": "breadth",
            "status": "failed",
            "level": "red",
            "latest_date": latest_trade_date,
            "stale_days": stale_days,
        }
    if stale_days <= 1:
        status = "done"
    elif stale_days <= 5:
        status = "degraded"
    else:
        status = "failed"
    return {
        "step": "breadth",
        "status": status,
        "level": _level(status if status != "done" else "done"),
        "latest_date": latest_trade_date,
        "target_date": target_date,
        "stale_days": stale_days,
        "merged_row_count": merged_row_count,
    }


def build_step_validations(
    pipeline_result: dict[str, Any],
    *,
    config: dict[str, Any],
    storage: Storage,
    snapshot_date: str,
) -> dict[str, Any]:
    top_expected = int(config.get("thresholds", {}).get("top_list_count", 10))
    rs_cfg = config.get("stock_rs", {})
    rs = pipeline_result.get("rs") or {}
    breadth = pipeline_result.get("breadth") or {}
    meta = storage.get_stock_rs_meta(snapshot_date) or {}

    picks = pipeline_result.get("picks_summary") or {}
    pick_total = int(picks.get("total") or 0)
    pick_errors = int(pipeline_result.get("stock_pick_errors") or 0)
    pick_stale = int(picks.get("stale") or 0)
    industries_with_tickers = int(picks.get("with_tickers") or 0)

    industry = validate_industry_step(
        industry_count=int(pipeline_result.get("industry_count") or 0),
        top_count=int(pipeline_result.get("top_count") or 0),
        top_expected=top_expected,
    )
    picks_step = validate_picks_step(
        pick_total=pick_total,
        pick_errors=pick_errors,
        pick_stale=pick_stale,
        industries_with_tickers=industries_with_tickers,
    )
    if rs.get("async_started"):
        rs_main = {
            "step": "rs_main",
            "status": "running",
            "level": "yellow",
            "computed_count": int(rs.get("computed_count") or 0),
            "universe_count": int(rs.get("universe_count") or 0),
            "coverage_ratio": 0.0,
            "no_bars_count": 0,
        }
    else:
        rs_main = validate_rs_main_step(
            computed_count=int(rs.get("computed_count") or meta.get("computed_count") or 0),
            universe_count=int(rs.get("universe_count") or meta.get("universe_count") or 0),
            coverage_ratio=float(rs.get("coverage_ratio") or meta.get("coverage_ratio") or 0.0),
            no_bars_count=int(rs.get("no_bars_count") or meta.get("no_bars_count") or 0),
        )
    rs_new = validate_rs_new_step(
        enabled=bool(rs_cfg.get("new_stock_enabled", True)),
        leaderboard_count=int(
            rs.get("new_stock_leaderboard_count") or meta.get("new_stock_leaderboard_count") or 0
        ),
        error=rs.get("new_stock_error"),
    )
    watchlist = validate_watchlist_step(
        watchlist_count=int(
            rs.get("watchlist_count") or storage.count_stock_watchlist(snapshot_date)
        ),
        picks_status=str(picks_step["status"]),
        rs_status=str(rs_main["status"]),
        pick_stale=pick_stale,
        pick_total=pick_total,
    )

    breadth_skipped = bool(pipeline_result.get("breadth_skipped"))
    latest_breadth = _latest_breadth_trade_date(storage)
    stale_days = _stale_days(latest_breadth, snapshot_date)
    breadth_step = validate_breadth_step(
        merged_row_count=int(breadth.get("merged_row_count") or 0),
        latest_trade_date=latest_breadth,
        target_date=snapshot_date,
        stale_days=stale_days if latest_breadth else 999,
        skipped=breadth_skipped,
    )

    steps = {
        "industry": industry,
        "picks": picks_step,
        "rs_main": rs_main,
        "rs_new": rs_new,
        "watchlist": watchlist,
        "breadth": breadth_step,
    }
    return {
        "steps": steps,
        "overall": aggregate_overall_status(steps),
        "cockpit_light": aggregate_cockpit_light(steps),
        "headline": build_headline(snapshot_date, steps),
    }


def aggregate_overall_status(steps: dict[str, dict[str, Any]]) -> str:
    core = [steps["industry"], steps["picks"], steps["rs_main"], steps["watchlist"]]
    if any(s.get("status") == "failed" for s in core):
        return "failed"
    optional = [steps["rs_new"], steps["breadth"]]
    if any(s.get("status") in {"degraded", "running"} for s in core + optional):
        return "degraded"
    return "ready"


def aggregate_cockpit_light(steps: dict[str, dict[str, Any]]) -> str:
    overall = aggregate_overall_status(steps)
    if overall == "failed":
        return "red"
    if overall == "degraded":
        return "yellow"
    return "green"


def build_headline(snapshot_date: str, steps: dict[str, dict[str, Any]]) -> str:
    overall = aggregate_overall_status(steps)
    watchlist_count = steps["watchlist"].get("count", 0)
    if overall == "ready":
        return f"As of {snapshot_date} · watchlist {watchlist_count}"
    if overall == "failed":
        failed = [k for k, v in steps.items() if v.get("status") == "failed"]
        return f"Update failed · {', '.join(failed)}"
    parts: list[str] = [f"As of {snapshot_date}"]
    if steps["breadth"].get("status") == "degraded":
        parts.append(f"breadth {steps['breadth'].get('stale_days', '?')}d stale")
    if steps["picks"].get("stale"):
        parts.append(f"picks stale {steps['picks']['stale']}")
    parts.append(f"watchlist {watchlist_count}")
    return " · ".join(parts)


def _cached_validation_is_stale(
    storage: Storage,
    snapshot_date: str,
    cached: dict[str, Any],
) -> bool:
    """True when persisted validation no longer matches RS / job state in DB."""
    steps = cached.get("steps") or {}
    rs_main = steps.get("rs_main") or {}
    cached_rs_status = str(rs_main.get("status") or "")
    meta = storage.get_stock_rs_meta(snapshot_date) or {}
    meta_computed = int(meta.get("computed_count") or 0)
    cached_computed = int(rs_main.get("computed_count") or 0)
    main_job = storage.get_latest_rs_job_run(snapshot_date, job_kind="main")
    main_done = bool(main_job and str(main_job.get("status") or "") == "done")

    if cached_rs_status == "running" and (main_done or meta_computed >= 500):
        return True
    if meta_computed > 0 and cached_computed > 0:
        delta = abs(meta_computed - cached_computed)
        if delta > max(50, int(cached_computed * 0.05)):
            return True

    run = storage.get_snapshot_run(snapshot_date)
    if run and str(run.get("current_step") or "") in {"awaiting_rs", "stock_rs_async_done"} and main_done:
        return True
    return False


def build_validation_from_storage(
    storage: Storage,
    *,
    config: dict[str, Any],
    snapshot_date: str,
    pipeline_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = storage.get_snapshot_run(snapshot_date)
    if pipeline_result:
        return build_step_validations(pipeline_result, config=config, storage=storage, snapshot_date=snapshot_date)
    if run and isinstance(run.get("details"), dict):
        cached = run["details"].get("validation")
        if isinstance(cached, dict) and cached.get("steps"):
            if not _cached_validation_is_stale(storage, snapshot_date, cached):
                return cached
    rows = storage.get_snapshot(snapshot_date)
    if not rows:
        return {
            "steps": {},
            "overall": "idle",
            "cockpit_light": "gray",
            "headline": f"No data for {snapshot_date} yet",
        }
    meta = storage.get_stock_rs_meta(snapshot_date) or {}
    synthetic = {
        "industry_count": len(rows),
        "top_count": int(config.get("thresholds", {}).get("top_list_count", 10)),
        "stock_pick_errors": 0,
        "picks_summary": {"total": 0, "stale": 0, "with_tickers": 0},
        "rs": {
            "computed_count": meta.get("computed_count", 0),
            "universe_count": meta.get("universe_count", 0),
            "coverage_ratio": meta.get("coverage_ratio", 0.0),
            "no_bars_count": meta.get("no_bars_count", 0),
            "watchlist_count": storage.count_stock_watchlist(snapshot_date),
            "new_stock_leaderboard_count": meta.get("new_stock_leaderboard_count", 0),
        },
        "breadth": {},
        "breadth_skipped": True,
    }
    picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    if picks:
        synthetic["picks_summary"] = {
            "total": len(picks),
            "stale": sum(
                1
                for v in picks.values()
                if str(v.get("error") or "").startswith("沿用缓存(")
            ),
            "with_tickers": sum(1 for v in picks.values() if v.get("tickers")),
        }
        synthetic["stock_pick_errors"] = sum(1 for v in picks.values() if v.get("error"))
    return build_step_validations(synthetic, config=config, storage=storage, snapshot_date=snapshot_date)


def _latest_breadth_trade_date(storage: Storage) -> str | None:
    rows = storage.get_breadth_daily(limit=1)
    if not rows:
        return None
    return str(rows[0].get("trade_date") or rows[0].get("raw_date") or "") or None


def _stale_days(latest_date: str | None, target_date: str) -> int:
    if not latest_date or not target_date:
        return 999
    try:
        from datetime import date

        latest = date.fromisoformat(latest_date[:10])
        target = date.fromisoformat(target_date[:10])
        return max(0, (target - latest).days)
    except ValueError:
        return 999
