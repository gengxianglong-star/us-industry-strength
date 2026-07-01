"""RS Top 100: liquid stock pool only, then pool-relative RS ranking."""

from __future__ import annotations

from typing import Any

from src.logging_config import get_logger
from src.services.elite_data import (
    elite_row_to_perf,
    fetch_elite_market_data,
    get_elite_market_cache,
    parse_finviz_number,
)
from src.stock_rs import _apply_market_rs_scores

logger = get_logger(__name__)

ETF_INDUSTRY = "Exchange Traded Fund"
RS_TOP_MIN_PRICE = 5.0
RS_TOP_MIN_DOLLAR_VOLUME = 100_000_000.0
RS_TOP_LIMIT = 100


def is_exchange_traded_fund(industry: str | None) -> bool:
    return str(industry or "").strip() == ETF_INDUSTRY


def passes_rs_top_stock_pool_filter(
    row: dict[str, Any],
    *,
    min_price: float = RS_TOP_MIN_PRICE,
    min_dollar_volume: float = RS_TOP_MIN_DOLLAR_VOLUME,
) -> bool:
    """Stock-only pool gate: not ETF, price > min_price, same-day turnover > min_dollar_volume."""
    if is_exchange_traded_fund(row.get("industry")):
        return False
    price = parse_finviz_number(row.get("price"))
    volume = parse_finviz_number(row.get("volume"))
    if price is None or volume is None:
        return False
    return price > min_price and price * volume > min_dollar_volume


def build_rs_top_100_rows(
    config: dict[str, Any],
    market: dict[str, dict[str, Any]] | None = None,
    *,
    limit: int = RS_TOP_LIMIT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Filter Elite universe to liquid stocks, compute RS within that pool, return Top N.

    Input: Elite market rows (symbol -> overview+perf+technical fields).
    Output: slim rows for API/Pages plus meta {pool_count, computed_count}.
    """
    data = market or get_elite_market_cache() or fetch_elite_market_data() or {}
    if not data:
        logger.warning("RS Top pool: Elite market data unavailable")
        return [], {"pool_count": 0, "computed_count": 0}

    rs_cfg = config.get("stock_rs", {})
    tier_a = float(rs_cfg.get("tier_a_score", 0.8))
    tier_b = float(rs_cfg.get("tier_b_score", 0.65))

    pool_count = 0
    perf_rows: list[dict[str, Any]] = []
    for sym, row in data.items():
        if not passes_rs_top_stock_pool_filter(row):
            continue
        pool_count += 1
        perf = elite_row_to_perf(sym, row)
        if perf is None:
            continue
        perf_rows.append(perf)

    if not perf_rows:
        return [], {"pool_count": pool_count, "computed_count": 0}

    _apply_market_rs_scores(perf_rows, config, tier_a=tier_a, tier_b=tier_b)
    perf_rows.sort(key=lambda item: (-item["rs_score"], item["rank_m"], item["symbol"]))

    out: list[dict[str, Any]] = []
    for rank, row in enumerate(perf_rows[: max(limit, 0)], start=1):
        elite_row = data.get(row["symbol"], {})
        price = parse_finviz_number(elite_row.get("price"))
        volume = parse_finviz_number(elite_row.get("volume"))
        item: dict[str, Any] = {
            "symbol": row["symbol"],
            "rs_rank": rank,
            "rs_score": round(float(row["rs_score"]), 4),
        }
        if price is not None:
            item["price"] = round(price, 2)
        if volume is not None:
            item["volume"] = int(volume)
        out.append(item)

    meta = {"pool_count": pool_count, "computed_count": len(perf_rows)}
    logger.info(
        "RS Top pool: pool=%d computed=%d exported=%d",
        pool_count,
        len(perf_rows),
        len(out),
    )
    return out, meta
