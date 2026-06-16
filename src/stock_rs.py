"""Compute US stock relative strength (RS) from Finviz Elite export only."""

from __future__ import annotations

from typing import Any, Callable

from src.config_loader import TIMEFRAMES, load_config
from src.logging_config import get_logger
from src.math_utils import percentile_rank, rank_dict_by_key, weighted_momentum_composite
from src.scoring import ScoredIndustry, filter_top_strong
from src.storage import Storage

logger = get_logger(__name__)


def _save_watchlist(
    storage: Storage,
    snapshot_date: str,
    watch_rows: list[dict[str, Any]],
) -> None:
    storage.save_stock_watchlist(snapshot_date, watch_rows)


def enrich_catalysts_for_snapshot(
    storage: Storage,
    snapshot_date: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pull Finviz news + LLM tags for the saved final watchlist (post-build only)."""
    cfg = (config or load_config()).get("catalyst") or {}
    max_symbols = int(cfg.get("max_symbols", 30))
    watchlist_count = storage.count_stock_watchlist(snapshot_date)
    if watchlist_count <= 0:
        logger.info("Catalyst enrichment skipped — no watchlist for %s", snapshot_date)
        return {
            "snapshot_date": snapshot_date,
            "watchlist_count": 0,
            "candidate_count": 0,
            "tagged_count": 0,
            "skipped": True,
            "reason": "empty_watchlist",
        }

    rows = storage.get_stock_watchlist(snapshot_date, limit=max(max_symbols, 120))
    slim_rows = [
        {"symbol": row["symbol"], "rs_score": row.get("rs_score")}
        for row in rows
        if row.get("symbol")
    ]
    candidates = slim_rows[:max_symbols]

    try:
        from src.services.catalyst_llm import enrich_watchlist_with_catalysts

        catalysts = enrich_watchlist_with_catalysts(candidates)
        if catalysts:
            storage.save_stock_catalysts(snapshot_date, catalysts)
        tagged_count = len(catalysts)
        logger.info(
            "Catalyst enrichment done for %s: %d/%d watchlist symbols tagged",
            snapshot_date,
            tagged_count,
            len(candidates),
        )
        return {
            "snapshot_date": snapshot_date,
            "watchlist_count": watchlist_count,
            "candidate_count": len(candidates),
            "tagged_count": tagged_count,
            "skipped": False,
        }
    except Exception:
        logger.warning("Catalyst enrichment failed for %s", snapshot_date, exc_info=True)
        return {
            "snapshot_date": snapshot_date,
            "watchlist_count": watchlist_count,
            "candidate_count": len(candidates),
            "tagged_count": 0,
            "skipped": True,
            "reason": "error",
        }


def _save_watchlist_and_enrich_catalysts(
    storage: Storage,
    snapshot_date: str,
    watch_rows: list[dict[str, Any]],
) -> None:
    _save_watchlist(storage, snapshot_date, watch_rows)


PERF_KEY_MAP = {
    "week": "perf_w",
    "month": "perf_m",
    "quarter": "perf_q",
    "half": "perf_h",
    "year": "perf_y",
}

NEW_STOCK_COHORTS: dict[str, dict[str, Any]] = {
    "M": {"timeframes": ("week", "month")},
    "Q": {"timeframes": ("week", "month", "quarter")},
    "H": {"timeframes": ("week", "month", "quarter", "half")},
    "3Q": {"timeframes": ("week", "month", "quarter", "half", "three_q")},
}

RANK_KEY_MAP = {
    "week": "rank_w",
    "month": "rank_m",
    "quarter": "rank_q",
    "half": "rank_h",
    "three_q": "rank_tq",
}


def _perf_key_for_timeframe(tf: str) -> str:
    if tf == "three_q":
        return "perf_tq"
    return PERF_KEY_MAP[tf]


def _rank_key_for_timeframe(tf: str) -> str:
    return RANK_KEY_MAP[tf]


def _apply_market_rs_scores(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    tier_a: float,
    tier_b: float,
) -> None:
    weights = config.get("_normalized_weights") or {
        "week": 0.05,
        "month": 0.3,
        "quarter": 0.4,
        "half": 0.2,
        "year": 0.05,
    }
    ranks = {tf: rank_dict_by_key(rows, PERF_KEY_MAP[tf]) for tf in TIMEFRAMES}
    for row in rows:
        row["composite_score"] = weighted_momentum_composite(row, weights)
    composite_ranks = rank_dict_by_key(rows, "composite_score")
    total = len(rows)
    for row in rows:
        symbol = row["symbol"]
        row["rank_w"] = ranks["week"][symbol]
        row["rank_m"] = ranks["month"][symbol]
        row["rank_q"] = ranks["quarter"][symbol]
        row["rank_h"] = ranks["half"][symbol]
        row["rank_y"] = ranks["year"][symbol]
        row["rs_score"] = percentile_rank(composite_ranks[symbol], total)
        if row["rs_score"] >= tier_a:
            row["tier"] = "A"
        elif row["rs_score"] >= tier_b:
            row["tier"] = "B"
        else:
            row["tier"] = "C"


def _normalized_weights_for_timeframes(
    config: dict[str, Any],
    timeframes: tuple[str, ...],
) -> dict[str, float]:
    base = config.get("_normalized_weights") or {
        "week": 0.05,
        "month": 0.3,
        "quarter": 0.4,
        "half": 0.2,
        "year": 0.05,
    }
    weight_map = {
        "week": base["week"],
        "month": base["month"],
        "quarter": base["quarter"],
        "half": base["half"],
        "three_q": base["year"],
    }
    picked = {tf: float(weight_map[tf]) for tf in timeframes}
    total = sum(picked.values())
    if total <= 0:
        n = len(timeframes)
        return {tf: 1.0 / n for tf in timeframes}
    return {tf: v / total for tf, v in picked.items()}


def _score_new_stock_rows(
    rows: list[dict[str, Any]],
    cohort: str,
    config: dict[str, Any],
    tier_a: float,
    tier_b: float,
) -> None:
    timeframes = NEW_STOCK_COHORTS[cohort]["timeframes"]
    weights = _normalized_weights_for_timeframes(config, timeframes)
    ranks = {
        tf: rank_dict_by_key(rows, _perf_key_for_timeframe(tf)) for tf in timeframes
    }
    total = len(rows)
    for row in rows:
        for tf in timeframes:
            rk = _rank_key_for_timeframe(tf)
            row[rk] = ranks[tf][row["symbol"]]
        row["rs_score"] = sum(
            weights[tf] * percentile_rank(ranks[tf][row["symbol"]], total) for tf in timeframes
        )
        if row["rs_score"] >= tier_a:
            row["tier"] = "A"
        elif row["rs_score"] >= tier_b:
            row["tier"] = "B"
        else:
            row["tier"] = "C"


def _should_defer_finviz_cross_watchlist(
    storage: Storage,
    snapshot_date: str,
    _config: dict[str, Any],
) -> bool:
    """finviz_cross watchlist needs industry picks — skip premature build during RS."""
    picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    if not picks:
        return True
    return not any(payload.get("tickers") for payload in picks.values())


def _top_industries_with_picks(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
) -> list[ScoredIndustry]:
    picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    return filter_top_strong(scored, config, stock_picks=picks)


def _build_main_watchlist_from_rows(
    ranked_rows: list[dict[str, Any]],
    storage: Storage,
    snapshot_date: str,
    scored_industries: list[ScoredIndustry],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    rs_cfg = config.get("stock_rs", {})
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    cross_top_percent = max(0.01, min(1.0, cross_top_percent))
    top_industries = _top_industries_with_picks(storage, snapshot_date, scored_industries, config)
    top_keys = {item.key for item in top_industries}
    symbol_to_industries = _industry_pick_map(storage, snapshot_date, top_keys)
    return _cross_watchlist_candidates(ranked_rows, symbol_to_industries, cross_top_percent)


def _industry_pick_map(
    storage: Storage,
    snapshot_date: str,
    top_keys: set[str],
) -> dict[str, list[str]]:
    picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    symbol_to_industries: dict[str, list[str]] = {}
    for key, payload in picks.items():
        if key not in top_keys:
            continue
        for symbol in payload.get("tickers", []) or []:
            symbol_to_industries.setdefault(symbol.upper(), []).append(key)
    return symbol_to_industries


def _cross_watchlist_candidates(
    ranked_rows: list[dict[str, Any]],
    symbol_to_industries: dict[str, list[str]],
    cross_top_percent: float,
) -> list[dict[str, Any]]:
    if not ranked_rows:
        return []
    cutoff = max(1, int(len(ranked_rows) * cross_top_percent))
    out: list[dict[str, Any]] = []
    for row in ranked_rows[:cutoff]:
        industries = symbol_to_industries.get(row["symbol"], [])
        if not industries:
            continue
        out.append(
            {
                "symbol": row["symbol"],
                "rs_score": float(row["rs_score"]),
                "industries": sorted(industries),
            }
        )
    return out


def _merge_watchlists(
    main_candidates: list[dict[str, Any]],
    new_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for row in main_candidates:
        by_symbol[row["symbol"]] = row
    for row in new_candidates:
        if row["symbol"] in by_symbol:
            continue
        by_symbol[row["symbol"]] = row
    merged = sorted(
        by_symbol.values(),
        key=lambda x: (-x["rs_score"], x["symbol"]),
    )
    for idx, row in enumerate(merged, start=1):
        row["rs_rank"] = idx
    return merged


def _elite_partial_candidate_symbols(issues_map: dict[str, str]) -> list[str]:
    return sorted(
        sym
        for sym, reason in issues_map.items()
        if reason in {"elite_no_perf", "insufficient_history", "perf_invalid"}
    )


def _build_elite_partial_inputs(
    elite_market: dict[str, dict[str, Any]] | None,
    issues_map: dict[str, str],
) -> dict[str, tuple[str, dict[str, float]]]:
    if not elite_market:
        return {}
    from src.services.elite_data import build_elite_partial_perf_inputs

    symbols = _elite_partial_candidate_symbols(issues_map)
    if not symbols:
        return {}
    partial = build_elite_partial_perf_inputs(elite_market, symbols)
    if partial:
        logger.info(
            "Elite shortened RS: %d symbols with partial perf (cohorts M/Q/H/3Q)",
            len(partial),
        )
    return partial


def _rs_provider_requires_elite(rs_cfg: dict[str, Any]) -> bool:
    return str(rs_cfg.get("rs_data_provider", "elite")).strip().lower() == "elite"


def _fetch_elite_market(rs_cfg: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    from src.services.elite_data import fetch_elite_market_data

    if not _rs_provider_requires_elite(rs_cfg):
        mode = str(rs_cfg.get("rs_data_provider", "elite")).strip().lower()
        if mode not in {"auto", "elite"}:
            logger.warning("rs_data_provider=%s is deprecated; using elite only", mode)
    return fetch_elite_market_data()


def _universe_rows_from_elite(market_data: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sym in sorted(market_data.keys()):
        row = market_data[sym]
        label = str(row.get("industry") or row.get("sector") or sym).strip() or sym
        rows.append({"symbol": sym, "name": label, "exchange": "ELITE"})
    return rows


def load_us_universe_with_cache(
    storage: Storage,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Elite market universe (for async RS job status / universe_count)."""
    from src.services.elite_data import fetch_elite_market_data, get_elite_market_cache

    _ = config
    market = get_elite_market_cache() or fetch_elite_market_data()
    if not market:
        cached = storage.list_stock_universe()
        return cached if cached else []
    universe = _universe_rows_from_elite(market)
    storage.upsert_stock_universe(universe, source="elite")
    return universe


def _incremental_rs_targets(
    storage: Storage,
    snapshot_date: str,
    symbols: list[str],
    symbol_set: set[str],
    *,
    incremental_mode: bool,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str], list[str]]:
    existing_rows = storage.get_stock_rs_raw(snapshot_date) if incremental_mode else []
    existing_perf_map: dict[str, dict[str, Any]] = {
        row["symbol"]: {
            "symbol": row["symbol"],
            "perf_w": float(row["perf_w"]),
            "perf_m": float(row["perf_m"]),
            "perf_q": float(row["perf_q"]),
            "perf_h": float(row["perf_h"]),
            "perf_y": float(row["perf_y"]),
        }
        for row in existing_rows
        if row["symbol"] in symbol_set
    }
    existing_issues = (
        {k: v for k, v in storage.get_stock_rs_issues(snapshot_date).items() if k in symbol_set}
        if incremental_mode
        else {}
    )
    if incremental_mode and (existing_perf_map or existing_issues):
        issue_symbols = {s for s in existing_issues.keys() if s in symbol_set}
        missing_symbols = {s for s in symbols if s not in existing_perf_map}
        target_symbols = sorted(issue_symbols | missing_symbols)
    else:
        target_symbols = list(symbols)
    return existing_rows, existing_perf_map, existing_issues, target_symbols


def _elite_rs_prefetch(
    target_symbols: list[str],
    perf_map: dict[str, dict[str, Any]],
    issues_map: dict[str, str],
    rs_cfg: dict[str, Any],
    *,
    elite_market: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[str], str, dict[str, Any]]:
    """Apply Finviz Elite perf to target symbols; no Yahoo/Stooq fallback."""
    stats: dict[str, Any] = {
        "elite_applied": 0,
        "elite_missing": 0,
        "elite_skipped_yahoo": 0,
    }
    from src.services.elite_data import build_perf_map_from_elite, fetch_elite_market_data

    market = elite_market if elite_market is not None else fetch_elite_market_data()
    if not market:
        return target_symbols, "elite", stats

    elite_perf, missing = build_perf_map_from_elite(market, target_symbols)
    for sym, row in elite_perf.items():
        perf_map[sym] = row
        issues_map.pop(sym, None)
    stats["elite_applied"] = len(elite_perf)
    stats["elite_missing"] = len(missing)
    for sym in missing:
        issues_map[sym] = "elite_no_perf"
    stats["elite_skipped_yahoo"] = len(missing)
    rs_source = "elite" if elite_perf else "elite"
    if elite_perf:
        logger.info(
            "⚡ Elite RS: %d ranked; %d skipped (no perf / illiquid)",
            stats["elite_applied"],
            stats["elite_skipped_yahoo"],
        )
    return [], rs_source, stats


def _rs_meta_payload(
    *,
    universe_count: int,
    computed_count: int,
    no_bars_count: int,
    insufficient_history_count: int,
    perf_invalid_count: int,
    coverage_ratio: float,
    new_stock_result: dict[str, Any] | None = None,
    rs_source: str = "elite",
    elite_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    new_stock_result = new_stock_result or {}
    return {
        "universe_count": universe_count,
        "computed_count": computed_count,
        "no_bars_count": no_bars_count,
        "insufficient_history_count": insufficient_history_count,
        "perf_invalid_count": perf_invalid_count,
        "coverage_ratio": coverage_ratio,
        "new_stock_m_count": int(new_stock_result.get("new_stock_m_count", 0) or 0),
        "new_stock_q_count": int(new_stock_result.get("new_stock_q_count", 0) or 0),
        "new_stock_h_count": int(new_stock_result.get("new_stock_h_count", 0) or 0),
        "new_stock_3q_count": int(new_stock_result.get("new_stock_3q_count", 0) or 0),
        "new_stock_leaderboard_count": int(
            new_stock_result.get("new_stock_leaderboard_count", 0) or 0
        ),
        "new_stock_watchlist_added": int(
            new_stock_result.get("new_stock_watchlist_added", 0) or 0
        ),
        "rs_source": rs_source,
        "elite_applied": int((elite_stats or {}).get("elite_applied", 0) or 0),
        "elite_missing": int((elite_stats or {}).get("elite_missing", 0) or 0),
        "elite_skipped_yahoo": int((elite_stats or {}).get("elite_skipped_yahoo", 0) or 0),
    }


def compute_and_store_new_stock_rs(
    storage: Storage,
    snapshot_date: str,
    config: dict[str, Any],
    cross_top_percent: float,
    scored_industries: list[ScoredIndustry],
    *,
    elite_partial: dict[str, tuple[str, dict[str, float]]] | None = None,
) -> dict[str, Any]:
    rs_cfg = config.get("stock_rs", {})
    tier_a = float(rs_cfg.get("tier_a_score", 0.8))
    tier_b = float(rs_cfg.get("tier_b_score", 0.65))
    if not bool(rs_cfg.get("new_stock_enabled", True)):
        return {
            "new_stock_m_count": 0,
            "new_stock_q_count": 0,
            "new_stock_h_count": 0,
            "new_stock_3q_count": 0,
            "new_stock_leaderboard_count": 0,
            "new_stock_rows": [],
            "new_watch_candidates": [],
        }

    cohort_rows: dict[str, list[dict[str, Any]]] = {k: [] for k in NEW_STOCK_COHORTS}
    for symbol, (cohort, perf) in (elite_partial or {}).items():
        row = {
            "symbol": symbol.upper(),
            "cohort": cohort,
            "bar_count": 0,
            "source": "elite_partial",
            "in_leaderboard": False,
        }
        row.update(perf)
        cohort_rows[cohort].append(row)

    counts = {c: len(cohort_rows[c]) for c in NEW_STOCK_COHORTS}
    all_scored: list[dict[str, Any]] = []
    leaderboard: list[dict[str, Any]] = []

    for cohort, rows in cohort_rows.items():
        if not rows:
            continue
        _score_new_stock_rows(rows, cohort, config, tier_a, tier_b)
        rows.sort(key=lambda x: (-x["rs_score"], x["symbol"]))
        cutoff = max(1, int(len(rows) * cross_top_percent))
        for row in rows:
            row["in_leaderboard"] = False
        for row in rows[:cutoff]:
            row["in_leaderboard"] = True
            leaderboard.append(row)
        all_scored.extend(rows)

    top_industries = _top_industries_with_picks(storage, snapshot_date, scored_industries, config)
    top_keys = {item.key for item in top_industries}
    symbol_to_industries = _industry_pick_map(storage, snapshot_date, top_keys)
    new_watch = _cross_watchlist_candidates(leaderboard, symbol_to_industries, cross_top_percent)

    storage.save_stock_rs_new_snapshot(snapshot_date, all_scored)
    return {
        "new_stock_m_count": counts["M"],
        "new_stock_q_count": counts["Q"],
        "new_stock_h_count": counts["H"],
        "new_stock_3q_count": counts["3Q"],
        "new_stock_leaderboard_count": len(leaderboard),
        "new_stock_rows": all_scored,
        "new_watch_candidates": new_watch,
    }


def backfill_new_stock_rs_for_snapshot(
    storage: Storage,
    snapshot_date: str,
    config: dict[str, Any],
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """对 perf 不全的股票用 Elite 已有周期做缩短版 RS，并合并观察名单。"""
    rs_cfg = config.get("stock_rs", {})
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    cross_top_percent = max(0.01, min(1.0, cross_top_percent))

    if progress_callback:
        progress_callback(0, 1)

    from src.services.elite_data import fetch_elite_market_data, get_elite_market_cache

    elite_market = get_elite_market_cache() or fetch_elite_market_data()
    issues = storage.get_stock_rs_issues(snapshot_date)
    elite_partial = _build_elite_partial_inputs(elite_market, issues)

    if progress_callback:
        progress_callback(1, 1)

    scored_rows = storage.get_snapshot(snapshot_date)

    class _Industry:
        def __init__(self, d: dict[str, Any]):
            self.key = d["industry_key"]
            self.name = d["name"]
            self.score = float(d.get("score") or 0)
            self.rank_m = int(d.get("rank_m") or 9999)
            self.rank_q = int(d.get("rank_q") or 9999)
            self.excluded = bool(d.get("excluded"))

    scored = [_Industry(r) for r in scored_rows if not r.get("excluded")]
    new_stock_result = compute_and_store_new_stock_rs(
        storage,
        snapshot_date,
        config,
        cross_top_percent,
        scored,
        elite_partial=elite_partial,
    )

    main_rows = storage.get_stock_rs_raw(snapshot_date)
    main_watch = _build_main_watchlist_from_rows(main_rows, storage, snapshot_date, scored, config)
    watch_rows = _merge_watchlists(main_watch, new_stock_result["new_watch_candidates"])
    _save_watchlist_and_enrich_catalysts(storage, snapshot_date, watch_rows)

    prev_meta = storage.get_stock_rs_meta(snapshot_date) or {}
    storage.save_stock_rs_meta(
        snapshot_date,
        {
            "universe_count": int(prev_meta.get("universe_count", 0)),
            "computed_count": int(prev_meta.get("computed_count", 0)),
            "no_bars_count": int(prev_meta.get("no_bars_count", 0)),
            "insufficient_history_count": int(prev_meta.get("insufficient_history_count", 0)),
            "perf_invalid_count": int(prev_meta.get("perf_invalid_count", 0)),
            "coverage_ratio": float(prev_meta.get("coverage_ratio", 0.0)),
            "new_stock_m_count": new_stock_result["new_stock_m_count"],
            "new_stock_q_count": new_stock_result["new_stock_q_count"],
            "new_stock_h_count": new_stock_result["new_stock_h_count"],
            "new_stock_3q_count": new_stock_result["new_stock_3q_count"],
            "new_stock_leaderboard_count": new_stock_result["new_stock_leaderboard_count"],
            "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
        },
    )

    return {
        **new_stock_result,
        "elite_partial_count": len(elite_partial),
        "watchlist_count": len(watch_rows),
    }


def compute_and_store_stock_rs(
    storage: Storage,
    snapshot_date: str,
    scored_industries: list[ScoredIndustry],
    config: dict[str, Any],
    *,
    force_full: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    rs_cfg = config.get("stock_rs", {})
    incremental_mode = bool(rs_cfg.get("incremental_mode", True)) and (not force_full)
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    cross_top_percent = max(0.01, min(1.0, cross_top_percent))
    tier_a = float(rs_cfg.get("tier_a_score", 0.8))
    tier_b = float(rs_cfg.get("tier_b_score", 0.65))

    elite_market = _fetch_elite_market(rs_cfg)
    if not elite_market:
        raise RuntimeError(
            "Elite 全市场 export 不可用。"
            "请检查 FINVIZ_AUTH_KEY（Export API token）与限流状态。"
        )

    logger.info("⚡ Elite universe: %d symbols", len(elite_market))
    universe = _universe_rows_from_elite(elite_market)
    symbols = [row["symbol"] for row in universe]
    symbol_set = set(symbols)
    storage.upsert_stock_universe(universe, source="elite")

    existing_rows, existing_perf_map, existing_issues, target_symbols = _incremental_rs_targets(
        storage,
        snapshot_date,
        symbols,
        symbol_set,
        incremental_mode=incremental_mode,
    )
    perf_map = dict(existing_perf_map)
    issues_map = dict(existing_issues)

    _target_remaining, rs_source, elite_stats = _elite_rs_prefetch(
        target_symbols,
        perf_map,
        issues_map,
        rs_cfg,
        elite_market=elite_market,
    )

    elite_done = int(elite_stats.get("elite_applied", 0) or 0)
    total_work = max(elite_done, len(target_symbols))
    if progress_callback:
        progress_callback(elite_done, total_work)

    rows = list(perf_map.values())
    coverage_ratio = (len(rows) / len(universe)) if universe else 0.0
    no_bars_count = sum(1 for r in issues_map.values() if r == "no_bars")
    insufficient_history_count = sum(
        1 for r in issues_map.values() if r == "insufficient_history"
    )
    perf_invalid_count = sum(1 for r in issues_map.values() if r == "perf_invalid")

    if not rows:
        if incremental_mode and existing_rows:
            storage.save_stock_rs_issues(snapshot_date, issues_map)
            prev_meta = storage.get_stock_rs_meta(snapshot_date) or {}
            preserved_count = len(existing_rows)
            return {
                "snapshot_date": snapshot_date,
                "universe_count": len(universe),
                "attempted_count": len(target_symbols),
                "computed_count": preserved_count,
                "watchlist_count": storage.count_stock_watchlist(snapshot_date),
                "no_bars_count": no_bars_count,
                "insufficient_history_count": insufficient_history_count,
                "perf_invalid_count": perf_invalid_count,
                "coverage_ratio": float(prev_meta.get("coverage_ratio", 0.0)),
                "new_stock_leaderboard_count": int(
                    prev_meta.get("new_stock_leaderboard_count", 0) or 0
                ),
                "new_stock_watchlist_added": int(
                    prev_meta.get("new_stock_watchlist_added", 0) or 0
                ),
                "preserved_existing_rs": True,
            }

        storage.save_stock_rs_snapshot(snapshot_date, [])
        storage.save_stock_rs_issues(snapshot_date, issues_map)
        elite_partial_inputs = _build_elite_partial_inputs(elite_market, issues_map)
        new_stock_result = compute_and_store_new_stock_rs(
            storage,
            snapshot_date,
            config,
            cross_top_percent,
            scored_industries,
            elite_partial=elite_partial_inputs,
        )
        defer_watchlist = _should_defer_finviz_cross_watchlist(storage, snapshot_date, config)
        if defer_watchlist:
            watch_rows: list[dict[str, Any]] = []
            logger.info(
                "Deferring watchlist build until Elite industry picks are stored (%s)",
                snapshot_date,
            )
        else:
            watch_rows = _merge_watchlists([], new_stock_result["new_watch_candidates"])
            _save_watchlist_and_enrich_catalysts(storage, snapshot_date, watch_rows)
        storage.save_stock_rs_meta(
            snapshot_date,
            _rs_meta_payload(
                universe_count=len(universe),
                computed_count=0,
                no_bars_count=no_bars_count,
                insufficient_history_count=insufficient_history_count,
                perf_invalid_count=perf_invalid_count,
                coverage_ratio=coverage_ratio,
                new_stock_result={
                    **new_stock_result,
                    "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
                },
                rs_source=rs_source,
                elite_stats=elite_stats,
            ),
        )
        return {
            "snapshot_date": snapshot_date,
            "universe_count": len(universe),
            "attempted_count": len(target_symbols),
            "computed_count": 0,
            "rs_source": rs_source,
            "watchlist_count": len(watch_rows),
            "no_bars_count": no_bars_count,
            "insufficient_history_count": insufficient_history_count,
            "perf_invalid_count": perf_invalid_count,
            "coverage_ratio": coverage_ratio,
            "new_stock_leaderboard_count": new_stock_result["new_stock_leaderboard_count"],
            "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
        }

    _apply_market_rs_scores(rows, config, tier_a=tier_a, tier_b=tier_b)
    rows.sort(key=lambda x: (-x["rs_score"], x["rank_m"], x["symbol"]))
    storage.save_stock_rs_snapshot(snapshot_date, rows)
    storage.save_stock_rs_issues(snapshot_date, issues_map)

    defer_watchlist = _should_defer_finviz_cross_watchlist(storage, snapshot_date, config)
    elite_partial_inputs = _build_elite_partial_inputs(elite_market, issues_map)
    new_stock_result = compute_and_store_new_stock_rs(
        storage,
        snapshot_date,
        config,
        cross_top_percent,
        scored_industries,
        elite_partial=elite_partial_inputs,
    )

    if defer_watchlist:
        watch_rows = []
        logger.info(
            "Deferring watchlist build until Elite industry picks are stored (%s)",
            snapshot_date,
        )
    else:
        main_watch_candidates = _build_main_watchlist_from_rows(
            rows,
            storage,
            snapshot_date,
            scored_industries,
            config,
        )
        watch_rows = _merge_watchlists(
            main_watch_candidates,
            new_stock_result["new_watch_candidates"],
        )
        _save_watchlist_and_enrich_catalysts(storage, snapshot_date, watch_rows)

    storage.save_stock_rs_meta(
        snapshot_date,
        _rs_meta_payload(
            universe_count=len(universe),
            computed_count=len(rows),
            no_bars_count=no_bars_count,
            insufficient_history_count=insufficient_history_count,
            perf_invalid_count=perf_invalid_count,
            coverage_ratio=coverage_ratio,
            new_stock_result={
                **new_stock_result,
                "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
            },
            rs_source=rs_source,
            elite_stats=elite_stats,
        ),
    )

    return {
        "snapshot_date": snapshot_date,
        "universe_count": len(universe),
        "attempted_count": len(target_symbols),
        "computed_count": len(rows),
        "rs_source": rs_source,
        "watchlist_count": len(watch_rows),
        "no_bars_count": no_bars_count,
        "insufficient_history_count": insufficient_history_count,
        "perf_invalid_count": perf_invalid_count,
        "coverage_ratio": coverage_ratio,
        "new_stock_leaderboard_count": new_stock_result["new_stock_leaderboard_count"],
        "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
    }


def rebuild_stock_watchlist_for_snapshot(
    storage: Storage,
    snapshot_date: str,
    scored_industries: list[ScoredIndustry],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild cross watchlist from existing RS rows and latest industry stock picks."""
    rows = storage.get_stock_rs_raw(snapshot_date)
    if not rows:
        return {
            "snapshot_date": snapshot_date,
            "watchlist_count": 0,
            "skipped": True,
            "reason": "no_rs_rows",
        }

    main_watch = _build_main_watchlist_from_rows(
        rows,
        storage,
        snapshot_date,
        scored_industries,
        config,
    )
    top_industries = _top_industries_with_picks(storage, snapshot_date, scored_industries, config)
    top_keys = {item.key for item in top_industries}
    symbol_to_industries = _industry_pick_map(storage, snapshot_date, top_keys)
    leaderboard = storage.get_stock_rs_new(
        snapshot_date,
        leaderboard_only=True,
        limit=5000,
    )
    new_watch_rows = [
        {"symbol": row["symbol"], "rs_score": float(row["rs_score"])}
        for row in leaderboard
    ]
    new_watch = _cross_watchlist_candidates(new_watch_rows, symbol_to_industries, 1.0)

    watch_rows = _merge_watchlists(main_watch, new_watch)
    _save_watchlist_and_enrich_catalysts(storage, snapshot_date, watch_rows)

    meta = storage.get_stock_rs_meta(snapshot_date)
    if meta:
        updated = dict(meta)
        updated["new_stock_watchlist_added"] = len(new_watch)
        storage.save_stock_rs_meta(snapshot_date, updated)

    return {
        "snapshot_date": snapshot_date,
        "watchlist_count": len(watch_rows),
        "skipped": False,
    }
