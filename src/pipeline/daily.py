"""Unified daily industry / picks / RS / breadth pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.breadth_data import sync_breadth_history
from src.finviz_scraper import fetch_industries
from src.scoring import filter_top_strong, score_industries
from src.stock_picks import fetch_top_industry_stock_picks
from src.stock_rs import backfill_new_stock_rs_for_snapshot, compute_and_store_stock_rs, load_us_universe_with_cache
from src.storage import Storage
from src.services.rs_jobs import RsJobService


@dataclass
class DailyPipelineOptions:
    skip_stocks: bool = False
    skip_rs: bool = False
    skip_breadth: bool = True
    full_breadth: bool = False
    force_full_rs: bool = False
    rs_async: bool = True
    verbose: bool = True


def _log(options: DailyPipelineOptions, message: str) -> None:
    if options.verbose:
        print(message)


def run_daily_pipeline(
    storage: Storage,
    config: dict[str, Any],
    snapshot_date: str,
    options: DailyPipelineOptions | None = None,
) -> dict[str, Any]:
    opts = options or DailyPipelineOptions()
    result: dict[str, Any] = {
        "snapshot_date": snapshot_date,
        "industry_count": 0,
        "top_count": 0,
        "stock_pick_count": 0,
        "stock_pick_errors": 0,
        "picks_summary": {"total": 0, "stale": 0, "with_tickers": 0},
        "rs": {},
        "breadth": {},
        "breadth_skipped": opts.skip_breadth,
    }

    storage.upsert_snapshot_run(
        snapshot_date,
        "running",
        current_step="industry_fetch",
        details={
            "skip_stocks": opts.skip_stocks,
            "skip_rs": opts.skip_rs,
            "skip_breadth": opts.skip_breadth,
            "full_breadth": opts.full_breadth,
        },
    )

    try:
        _log(opts, "正在抓取 Finviz 行业数据…")
        rows = fetch_industries(config)
        scored = score_industries(rows, config)
        top = filter_top_strong(scored, config)
        storage.save_snapshot(snapshot_date, scored)
        result["industry_count"] = len(rows)
        result["top_count"] = len(top)
        _log(opts, f"共获取 {len(rows)} 个行业，Top {len(top)}")

        storage.upsert_snapshot_run(
            snapshot_date,
            "running",
            current_step="stock_picks",
            details={"top_count": len(top)},
        )

        picks: dict[str, dict[str, Any]] = {}
        if not opts.skip_stocks and top:
            _log(opts, f"正在抓取 Top {len(top)} 强势行业的筛选个股…")
            picks = fetch_top_industry_stock_picks(storage, snapshot_date, scored, config)
            result["stock_pick_count"] = sum(len(v.get("tickers") or []) for v in picks.values())
            result["stock_pick_errors"] = sum(1 for v in picks.values() if v.get("error"))
            result["picks_summary"] = {
                "total": len(picks),
                "stale": sum(
                    1
                    for v in picks.values()
                    if str(v.get("error") or "").startswith("沿用缓存(")
                ),
                "with_tickers": sum(1 for v in picks.values() if v.get("tickers")),
            }
            for key, payload in picks.items():
                name = next((c.name for c in top if c.key == key), key)
                tickers = payload.get("tickers", [])
                err = payload.get("error")
                stale = payload.get("stale_fallback")
                if err:
                    suffix = " [stale]" if stale else ""
                    _log(opts, f"  {name}: 失败 ({err}){suffix}")
                else:
                    _log(opts, f"  {name} ({len(tickers)}): {', '.join(tickers) if tickers else '（无匹配）'}")

        rs_result: dict[str, Any] = {}
        if not opts.skip_rs:
            storage.upsert_snapshot_run(snapshot_date, "running", current_step="stock_rs")
            if opts.rs_async:
                _log(opts, "已启动后台 RS 任务（行业与筛股可先展示）…")
                kick = RsJobService().start_compute_rs(
                    storage=storage,
                    snapshot_date=snapshot_date,
                    scored=scored,
                    config=config,
                    force_full=opts.force_full_rs,
                    async_mode=True,
                )
                universe = load_us_universe_with_cache(storage, config)
                rs_result = {
                    "async_started": True,
                    "status": kick.get("status"),
                    "job_id": kick.get("job_id"),
                    "universe_count": len(universe),
                    "computed_count": storage.count_stock_rs(snapshot_date),
                    "watchlist_count": storage.count_stock_watchlist(snapshot_date),
                }
            else:
                _log(opts, "正在计算全市场个股相对强度（RS）…")
                rs_result = compute_and_store_stock_rs(
                    storage,
                    snapshot_date,
                    scored,
                    config,
                    force_full=opts.force_full_rs,
                )
                if config.get("stock_rs", {}).get("new_stock_enabled", True):
                    if int(rs_result.get("new_stock_leaderboard_count", 0) or 0) <= 0:
                        if int(rs_result.get("insufficient_history_count", 0) or 0) > 0:
                            _log(opts, "正在补算新股 RS…")
                            try:
                                new_rs = backfill_new_stock_rs_for_snapshot(
                                    storage,
                                    snapshot_date,
                                    config,
                                )
                                rs_result = {**rs_result, **new_rs}
                            except Exception as exc:  # noqa: BLE001
                                rs_result = {**rs_result, "new_stock_error": str(exc)}
            result["rs"] = rs_result
            if not rs_result.get("async_started"):
                _log(
                    opts,
                    "RS 完成："
                    f"Universe={rs_result.get('universe_count', 0)} "
                    f"Computed={rs_result.get('computed_count', 0)} "
                    f"Watchlist={rs_result.get('watchlist_count', 0)}",
                )

        breadth_result: dict[str, Any] = {}
        if not opts.skip_breadth:
            storage.upsert_snapshot_run(snapshot_date, "running", current_step="breadth_sync")
            breadth_result = sync_breadth_history(storage, full=opts.full_breadth, config=config)
            result["breadth"] = breadth_result
            validation = breadth_result.get("validation") or {}
            _log(
                opts,
                f"市场宽度同步 mode={breadth_result.get('mode')} "
                f"merged={breadth_result.get('merged_row_count', 0)} "
                f"validation_ok={validation.get('ok')}",
            )
            if not bool(validation.get("ok", True)):
                raise RuntimeError("breadth validation failed")

        if not (opts.rs_async and rs_result.get("async_started")):
            storage.upsert_snapshot_run(
                snapshot_date,
                "completed",
                current_step="done",
                details={
                    "industry_count": result["industry_count"],
                    "top_count": result["top_count"],
                    "stock_pick_count": result["stock_pick_count"],
                    "stock_pick_errors": result["stock_pick_errors"],
                    "rs_computed_count": int(rs_result.get("computed_count", 0) or 0),
                    "breadth_merged_count": int(breadth_result.get("merged_row_count", 0) or 0),
                },
                finished=True,
            )
        return result
    except Exception as exc:  # noqa: BLE001
        storage.upsert_snapshot_run(
            snapshot_date,
            "failed",
            current_step="failed",
            error=str(exc),
            finished=True,
        )
        raise
