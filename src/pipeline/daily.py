"""Unified daily industry / picks / RS / breadth pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.breadth_data import sync_breadth_history
from src.services.elite_data import elite_auth_key
from src.services.elite_groups import fetch_elite_industry_rows
from src.logging_config import get_logger
from src.scoring import filter_top_strong, score_industries
from src.stock_picks import apply_elite_picks_after_rs
from src.stock_rs import (
    backfill_new_stock_rs_for_snapshot,
    compute_and_store_stock_rs,
    load_us_universe_with_cache,
)
from src.storage import Storage
from src.services.rs_jobs import RsJobService

logger = get_logger(__name__)


@dataclass
class DailyPipelineOptions:
    skip_stocks: bool = True  # deprecated: Elite picks always run after RS
    skip_rs: bool = False
    skip_breadth: bool = True
    full_breadth: bool = False
    force_full_rs: bool = False
    rs_async: bool = True
    verbose: bool = True


def _log(options: DailyPipelineOptions, message: str) -> None:
    if options.verbose:
        logger.info(message)


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
            "skip_rs": opts.skip_rs,
            "skip_breadth": opts.skip_breadth,
            "full_breadth": opts.full_breadth,
            "pipeline_mode": "elite_only",
        },
    )

    try:
        _log(opts, "正在抓取行业数据…")
        rows = fetch_elite_industry_rows()
        if rows:
            _log(opts, f"Elite Groups 已加载 {len(rows)} 个行业")
        elif elite_auth_key():
            raise RuntimeError(
                "Elite 行业组抓取失败（FINVIZ_AUTH_KEY 已配置）。"
                "请运行 scripts/verify_finviz_elite_exports.py --full 排查 token/限流。"
            )
        else:
            raise RuntimeError(
                "未配置 FINVIZ_AUTH_KEY，无法运行 Elite 管道。"
                "请在 .env 或 GitHub Secrets 中设置 Export API token。"
            )
        scored = score_industries(rows, config)
        top = filter_top_strong(scored, config)
        storage.save_snapshot(snapshot_date, scored)
        result["industry_count"] = len(rows)
        result["top_count"] = len(top)

        storage.upsert_snapshot_run(
            snapshot_date,
            "running",
            current_step="stock_rs",
            details={"top_count": len(top)},
        )
        _log(opts, f"共获取 {len(rows)} 个行业，Top {len(top)}")

        rs_result: dict[str, Any] = {}
        if not opts.skip_rs:
            if opts.rs_async:
                _log(opts, "已启动后台 RS 任务（完成后自动跑 Elite 行业筛股）…")
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
                        issues = storage.get_stock_rs_issues(snapshot_date)
                        from src.stock_rs import _elite_partial_candidate_symbols

                        if _elite_partial_candidate_symbols(issues):
                            _log(opts, "正在补算新股 RS…")
                            try:
                                new_rs = backfill_new_stock_rs_for_snapshot(
                                    storage,
                                    snapshot_date,
                                    config,
                                )
                                rs_result = {**rs_result, **new_rs}
                            except Exception as exc:  # noqa: BLE001
                                logger.exception("new stock RS backfill failed")
                                rs_result = {**rs_result, "new_stock_error": str(exc)}

                _log(opts, "正在用 Elite export 抓取 Top 行业个股…")
                elite_out = apply_elite_picks_after_rs(
                    storage,
                    snapshot_date,
                    scored,
                    config,
                )
                picks = elite_out.get("picks") or {}
                top = filter_top_strong(scored, config, stock_picks=picks)
                result["top_count"] = elite_out.get("top_count", len(top))
                result["stock_pick_count"] = elite_out.get("stock_pick_count", 0)
                result["stock_pick_errors"] = elite_out.get("stock_pick_errors", 0)
                result["picks_summary"] = elite_out.get("picks_summary") or {}
                rs_result["watchlist_count"] = elite_out.get(
                    "watchlist_count",
                    rs_result.get("watchlist_count", 0),
                )
                if elite_out.get("catalyst"):
                    result["catalyst"] = elite_out["catalyst"]
                    cat = elite_out["catalyst"]
                    _log(
                        opts,
                        "观察名单催化剂："
                        f"{cat.get('tagged_count', 0)}/{cat.get('candidate_count', 0)} "
                        f"（最终名单 {cat.get('watchlist_count', 0)} 只）",
                    )
                _log(
                    opts,
                    f"Elite 行业筛股完成：Top {result['top_count']}，"
                    f"Watchlist={rs_result.get('watchlist_count', 0)}",
                )

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
            try:
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
                    logger.warning("市场宽度数据校验未通过，但保留已有的行业与个股数据")
                    result["breadth_error"] = "validation failed"
            except Exception as breadth_exc:
                logger.error("市场宽度同步发生异常，跳过此步骤: %s", breadth_exc)
                result["breadth_error"] = str(breadth_exc)

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
                    "breadth_error": result.get("breadth_error"),
                },
                finished=True,
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("daily pipeline failed for snapshot_date=%s", snapshot_date)
        storage.upsert_snapshot_run(
            snapshot_date,
            "failed",
            current_step="failed",
            error=str(exc),
            finished=True,
        )
        raise
