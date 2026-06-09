"""Tests for yfinance cache guard."""

from __future__ import annotations

from src.yfinance_util import disable_yfinance_disk_cache, set_tz_cache


def test_disable_yfinance_disk_cache_uses_dummy_backends() -> None:
    from yfinance.cache import (
        _CookieCacheDummy,
        _CookieCacheManager,
        _ISINCacheDummy,
        _ISINCacheManager,
        _TzCacheDummy,
        _TzCacheManager,
    )

    set_tz_cache(False)
    assert isinstance(_TzCacheManager._tz_cache, _TzCacheDummy)
    assert isinstance(_CookieCacheManager._Cookie_cache, _CookieCacheDummy)
    assert isinstance(_ISINCacheManager._isin_cache, _ISINCacheDummy)
    disable_yfinance_disk_cache()
