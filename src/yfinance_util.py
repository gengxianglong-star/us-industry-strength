"""Safe yfinance batch downloads (no SQLite cache contention on macOS/CI)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf

from src.logging_config import get_logger

logger = get_logger(__name__)

_disk_cache_disabled = False


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
    """Batch OHLC download with disk cache off and conservative threading."""
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
