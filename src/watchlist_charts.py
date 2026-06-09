"""Watchlist chart hooks — frontend Finviz/TradingView image embeds (no backend OHLC fetch)."""

from __future__ import annotations

from typing import Any

from src.logging_config import get_logger

logger = get_logger(__name__)


def chart_bar_coverage(watchlist: list[dict[str, Any]], *, min_bars: int = 10) -> dict[str, int]:
    """Legacy export metric; charts are rendered client-side via Finviz."""
    total = len(watchlist or [])
    return {"total": total, "with_chart_bars": 0}


def attach_watchlist_chart_bars(watchlist: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    return watchlist


def enrich_watchlist_chart_bars(watchlist: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    if watchlist:
        logger.info(
            "frontend chart embed mode: skipping backend K-line download for %d watchlist symbols",
            len(watchlist),
        )
    return watchlist
