"""Watchlist daily chart bars for static export and API responses."""

from __future__ import annotations

import time
from typing import Any

from src.logging_config import get_logger
from src.yfinance_util import MIN_CHART_BARS, download_ticker_frames

logger = get_logger(__name__)

CHART_BAR_LIMIT = 80


def _df_to_chart_bars(df) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    tail = df.tail(CHART_BAR_LIMIT)
    for idx, row in tail.iterrows():
        try:
            o = float(row["Open"])
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(x == x for x in (o, h, l, c)):  # NaN check
            continue
        date_key = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        bars.append({"d": date_key, "o": o, "h": h, "l": l, "c": c})
    return bars


def chart_bar_coverage(watchlist: list[dict[str, Any]], *, min_bars: int = 10) -> dict[str, int]:
    total = len(watchlist or [])
    with_bars = sum(
        1 for row in watchlist or [] if len(row.get("chart_bars") or []) >= min_bars
    )
    return {"total": total, "with_chart_bars": with_bars}


def _attach_bars(watchlist: list[dict[str, Any]], *, log_label: str) -> list[dict[str, Any]]:
    if not watchlist:
        return watchlist

    symbols = [str(row.get("symbol") or "").upper() for row in watchlist if row.get("symbol")]
    if not symbols:
        return watchlist

    t0 = time.perf_counter()
    frames = download_ticker_frames(symbols, period="6mo", chunk_size=12, min_rows=MIN_CHART_BARS)
    enriched: list[dict[str, Any]] = []
    for row in watchlist:
        sym = str(row.get("symbol") or "").upper()
        df = frames.get(sym)
        if df is not None and len(df) >= MIN_CHART_BARS:
            item = dict(row)
            item["chart_bars"] = _df_to_chart_bars(df)
            enriched.append(item)
        else:
            enriched.append(row)

    cov = chart_bar_coverage(enriched)
    logger.info(
        "%s: chart bars for %d/%d watchlist symbols (%.1fs)",
        log_label,
        cov["with_chart_bars"],
        cov["total"],
        time.perf_counter() - t0,
    )
    return enriched


def attach_watchlist_chart_bars(watchlist: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    return _attach_bars(watchlist, log_label="attach_watchlist_chart_bars")


def enrich_watchlist_chart_bars(watchlist: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    return _attach_bars(watchlist, log_label="export_watchlist_chart_bars")
