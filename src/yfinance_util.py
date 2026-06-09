"""Safe yfinance batch downloads (no SQLite cache contention on macOS/CI)."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import yfinance as yf

from src.logging_config import get_logger

logger = get_logger(__name__)

_disk_cache_disabled = False
DEFAULT_CHUNK_SIZE = 15
MIN_CHART_BARS = 10


def disable_yfinance_disk_cache() -> None:
    """Disable Tz/Cookie/ISIN SQLite caches to avoid 'too many open files'."""
    global _disk_cache_disabled
    if _disk_cache_disabled:
        return
    from yfinance.cache import (
        _CookieCacheDummy,
        _CookieCacheManager,
        _ISINCacheDummy,
        _ISINCacheManager,
        _TzCacheDummy,
        _TzCacheManager,
    )

    _TzCacheManager._tz_cache = _TzCacheDummy()
    _CookieCacheManager._Cookie_cache = _CookieCacheDummy()
    _ISINCacheManager._isin_cache = _ISINCacheDummy()
    _disk_cache_disabled = True
    logger.debug("yfinance disk caches disabled (dummy backends)")


def set_tz_cache(enabled: bool) -> None:
    """Compat helper: ``set_tz_cache(False)`` disables timezone SQLite cache."""
    if not enabled:
        disable_yfinance_disk_cache()


def ticker_dataframe(data: pd.DataFrame, symbol: str, tickers: list[str]) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    sym = symbol.upper()
    if len(tickers) == 1:
        df = data.copy()
    elif isinstance(data.columns, pd.MultiIndex):
        if sym not in data.columns.get_level_values(0):
            return pd.DataFrame()
        df = data[sym].copy()
    else:
        return pd.DataFrame()
    if "Close" not in df.columns:
        return pd.DataFrame()
    return df.dropna(subset=["Close"])


def download_prices(
    tickers: str | list[str],
    *,
    period: str,
    interval: str = "1d",
    group_by: str = "ticker",
    auto_adjust: bool = True,
    timeout: int | None = None,
    threads: bool = False,
) -> pd.DataFrame:
    """Batch OHLC download with disk cache off and single-threaded yfinance."""
    disable_yfinance_disk_cache()
    if isinstance(tickers, list):
        tickers = [t for t in tickers if t]
    if not tickers:
        return pd.DataFrame()

    kwargs: dict[str, Any] = {
        "period": period,
        "interval": interval,
        "group_by": group_by,
        "threads": threads,
        "progress": False,
        "auto_adjust": auto_adjust,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return yf.download(tickers, **kwargs)


def download_ticker_frames(
    tickers: list[str],
    *,
    period: str,
    timeout: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_rows: int = MIN_CHART_BARS,
    pause_seconds: float = 0.2,
) -> dict[str, pd.DataFrame]:
    """Chunked batch download with per-symbol fallback for missing tickers."""
    disable_yfinance_disk_cache()
    unique = [str(t).upper() for t in tickers if t]
    if not unique:
        return {}

    frames: dict[str, pd.DataFrame] = {}
    for start in range(0, len(unique), chunk_size):
        chunk = unique[start : start + chunk_size]
        logger.info(
            "yfinance download chunk %d-%d/%d (%s)",
            start + 1,
            start + len(chunk),
            len(unique),
            ",".join(chunk[:5]) + ("…" if len(chunk) > 5 else ""),
        )
        try:
            data = download_prices(
                chunk,
                period=period,
                group_by="ticker",
                auto_adjust=True,
                timeout=timeout,
                threads=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance chunk failed: %s", exc)
            data = pd.DataFrame()

        for sym in chunk:
            df = ticker_dataframe(data, sym, chunk)
            if not df.empty:
                frames[sym] = df
        time.sleep(pause_seconds)

    missing = [sym for sym in unique if len(frames.get(sym, pd.DataFrame())) < min_rows]
    if missing:
        logger.info("yfinance single-symbol retry for %d tickers", len(missing))
    for sym in missing:
        try:
            data = download_prices(
                [sym],
                period=period,
                group_by="ticker",
                auto_adjust=True,
                timeout=timeout,
                threads=False,
            )
            df = ticker_dataframe(data, sym, [sym])
            if not df.empty:
                frames[sym] = df
        except Exception as exc:  # noqa: BLE001
            logger.debug("yfinance single download failed for %s: %s", sym, exc)
        time.sleep(0.15)

    ok = sum(1 for sym in unique if len(frames.get(sym, pd.DataFrame())) >= min_rows)
    logger.info("yfinance fetched %d/%d tickers with>=%d rows", ok, len(unique), min_rows)
    return frames
