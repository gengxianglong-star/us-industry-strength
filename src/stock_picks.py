"""Elite industry stock picks and watchlist pairing."""

from __future__ import annotations

from typing import Any

from src.logging_config import get_logger
from src.scoring import ScoredIndustry, top_strong_sort_key
from src.stock_filters import build_screener_filters
from src.storage import Storage

logger = get_logger(__name__)


def normalize_industry_label(text: str) -> str:
    import re

    cleaned = text.strip().lower().replace("&", " and ")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _build_elite_industry_index(
    market: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    by_industry: dict[str, list[str]] = {}
    for sym, row in market.items():
        raw = str(row.get("industry") or "").strip()
        if not raw:
            continue
        sym_u = sym.upper()
        for key in {raw.lower(), normalize_industry_label(raw)}:
            if not key:
                continue
            bucket = by_industry.setdefault(key, [])
            if sym_u not in bucket:
                bucket.append(sym_u)
    return by_industry


def _rank_industry_tickers(
    candidates: list[str],
    *,
    rs_map: dict[str, dict[str, Any]],
    per_industry_cap: int | None = None,
) -> list[str]:
    """Rank screener export tickers by main RS (no RS score floor)."""
    ranked: list[tuple[str, float]] = []
    for sym in candidates:
        rs_row = rs_map.get(sym.upper()) or rs_map.get(sym)
        if not rs_row:
            continue
        rs_score = float(rs_row.get("rs_score", 0) or 0)
        ranked.append((sym.upper(), rs_score))
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    tickers = [sym for sym, _ in ranked]
    if per_industry_cap is not None and per_industry_cap > 0:
        tickers = tickers[:per_industry_cap]
    return tickers


def _resolve_qualified_industry_tickers(
    item: ScoredIndustry,
    *,
    rs_map: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[str], str, list[str]]:
    from src.services.elite_data import fetch_elite_industry_tickers

    candidate_source = "elite_screener_export"
    candidates = fetch_elite_industry_tickers(item.key, config)
    tickers = _rank_industry_tickers(
        candidates,
        rs_map=rs_map,
    )
    return tickers, candidate_source, candidates


def _stale_fallback_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("scraper", {}).get("stale_fallback_enabled", True))


def fetch_and_store_elite_stock_picks(
    storage: Storage,
    snapshot_date: str,
    industry_keys: list[str],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Manual/UI refresh via Elite per-industry export."""
    if not industry_keys:
        return {}

    rows = storage.get_snapshot(snapshot_date) or []
    scored_by_key = {
        str(row["industry_key"]): ScoredIndustry(
            key=str(row["industry_key"]),
            name=str(row.get("name") or row["industry_key"]),
            stocks=int(row.get("stocks") or 0),
            perf_w=float(row.get("perf_w") or 0),
            perf_m=float(row.get("perf_m") or 0),
            perf_q=float(row.get("perf_q") or 0),
            perf_h=float(row.get("perf_h") or 0),
            perf_y=float(row.get("perf_y") or 0),
            rank_w=int(row.get("rank_w") or 9999),
            rank_m=int(row.get("rank_m") or 9999),
            rank_q=int(row.get("rank_q") or 9999),
            rank_h=int(row.get("rank_h") or 9999),
            rank_y=int(row.get("rank_y") or 9999),
            score=float(row.get("score") or 0),
            tier=str(row.get("tier") or ""),
            tags=list(row.get("tags") or []),
            excluded=bool(row.get("excluded")),
            exclude_reason=row.get("exclude_reason"),
            finviz_url=str(row.get("finviz_url") or ""),
        )
        for row in rows
    }

    subset = [scored_by_key[key] for key in industry_keys if key in scored_by_key]
    if not subset:
        return {}

    batch = build_and_store_elite_industry_picks(
        storage,
        snapshot_date,
        subset,
        config,
    )
    return {
        key: {
            "tickers": payload.get("tickers") or [],
            "screener_url": payload.get("screener_url"),
            "filters": payload.get("filters"),
            "elite_source": True,
            "candidate_source": payload.get("candidate_source", "elite_screener_export"),
        }
        for key, payload in batch.items()
    }


def build_and_store_elite_industry_picks(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
    *,
    elite_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build Top-N industries that each have screener picks; scan lower ranks to backfill slots."""
    from src.services.elite_data import (
        build_elite_industry_screener_url,
        elite_auth_key,
        fetch_elite_market_data,
        get_elite_market_cache,
    )

    market = elite_market or get_elite_market_cache() or fetch_elite_market_data()
    if not market:
        return {}

    rs_map = {
        str(row["symbol"]).upper(): row for row in storage.get_stock_rs_raw(snapshot_date)
    }
    auth_key = elite_auth_key() or ""

    active = [item for item in scored if not item.excluded]
    active.sort(key=lambda item: top_strong_sort_key(item.score, item.rank_m, item.rank_q, item.key))
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    results: dict[str, dict[str, Any]] = {}
    filled = 0
    skipped_empty = 0
    stale_used = 0

    for item in active:
        if filled >= top_n:
            break

        tickers, candidate_source, _candidates = _resolve_qualified_industry_tickers(
            item,
            rs_map=rs_map,
            config=config,
        )

        filters = build_screener_filters(item.key, config)
        screener_url = (
            build_elite_industry_screener_url(item.key, config, auth_key)
            if auth_key
            else f"elite://export/industry/{item.key}"
        )

        if not tickers:
            skipped_empty += 1
            logger.info(
                "Elite picks: skipping industry %s (rank scan) — no screener symbols with RS data",
                item.name,
            )
            if _stale_fallback_enabled(config):
                stale = storage.get_latest_successful_industry_stock_picks(
                    item.key,
                    before_snapshot_date=snapshot_date,
                )
                if stale and stale.get("tickers"):
                    ranked_stale = _rank_industry_tickers(
                        list(stale["tickers"]),
                        rs_map=rs_map,
                    )
                    if ranked_stale:
                        tickers = ranked_stale
                        candidate_source = "stale_fallback_ranked"
                        stale_used += 1
                        screener_url = str(stale.get("screener_url") or screener_url)
                        filters = str(stale.get("filters") or filters)
                        logger.info(
                            "Elite picks: stale fallback for %s (%d/%d tickers re-qualified from %s)",
                            item.name,
                            len(tickers),
                            len(stale["tickers"]),
                            stale.get("snapshot_date"),
                        )
            if not tickers:
                continue

        storage.save_industry_stock_picks(
            snapshot_date,
            item.key,
            tickers,
            screener_url,
            filters,
        )
        results[item.key] = {
            "tickers": tickers,
            "screener_url": screener_url,
            "filters": filters,
            "elite_source": True,
            "candidate_source": candidate_source,
        }
        filled += 1

    logger.info(
        "Elite industry picks: %d industries selected (%d skipped empty, %d stale), %d tickers",
        len(results),
        skipped_empty,
        stale_used,
        sum(len(payload.get("tickers") or []) for payload in results.values()),
    )
    return results


def apply_elite_picks_after_rs(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
    *,
    elite_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run Elite per-industry export picks, rebuild watchlist, enrich catalysts."""
    from src.scoring import filter_top_strong
    from src.stock_rs import enrich_catalysts_for_snapshot, rebuild_stock_watchlist_for_snapshot

    picks = build_and_store_elite_industry_picks(
        storage,
        snapshot_date,
        scored,
        config,
        elite_market=elite_market,
    )
    top = filter_top_strong(scored, config, stock_picks=picks)
    rebuild = rebuild_stock_watchlist_for_snapshot(storage, snapshot_date, scored, config)
    catalyst: dict[str, Any] = {}
    if int(rebuild.get("watchlist_count", 0) or 0) > 0:
        catalyst = enrich_catalysts_for_snapshot(storage, snapshot_date, config)
    return {
        "picks": picks,
        "top_count": len(top),
        "stock_pick_count": sum(len(v.get("tickers") or []) for v in picks.values()),
        "stock_pick_errors": max(0, len(top) - len(picks)),
        "picks_summary": {
            "total": len(picks),
            "stale": sum(
                1
                for payload in picks.values()
                if payload.get("candidate_source") == "stale_fallback_ranked"
            ),
            "with_tickers": sum(1 for payload in picks.values() if payload.get("tickers")),
        },
        "watchlist_count": rebuild.get("watchlist_count", 0),
        "catalyst": catalyst,
    }
