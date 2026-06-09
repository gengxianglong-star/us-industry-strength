"""Unit tests for RS technical watchlist filters."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.watchlist_build import (
    AVG_DOLLAR_VOLUME_DAYS,
    MIN_BARS_FOR_SMA200,
    build_rs_technical_watchlist,
    passes_technical_momentum_filters,
)


def _uptrend_df(count: int = 220, *, volume: float = 2_000_000) -> pd.DataFrame:
    closes = [100.0 + i * 0.5 for i in range(count)]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [volume] * count,
        }
    )


def test_passes_technical_momentum_filters_happy_path() -> None:
    df = _uptrend_df()
    assert passes_technical_momentum_filters(df, 100_000_000)


def test_passes_technical_momentum_filters_rejects_low_avg_volume() -> None:
    df = _uptrend_df(volume=10_000)
    assert not passes_technical_momentum_filters(df, 100_000_000)


def test_passes_technical_momentum_filters_needs_200_bars() -> None:
    df = _uptrend_df(count=MIN_BARS_FOR_SMA200 - 1)
    assert not passes_technical_momentum_filters(df, 100_000_000)


def test_build_rs_technical_watchlist_early_stops_at_cap() -> None:
    ranked = [{"symbol": f"S{i}", "rs_score": 1.0 - i * 0.01} for i in range(30)]
    good_df = _uptrend_df()

    def fake_download(tickers, **kwargs):  # noqa: ANN001, ARG001
        frames = {}
        for sym in tickers:
            frames[sym] = good_df
        return pd.concat(frames, axis=1)

    config = {
        "stock_rs": {
            "cross_top_percent": 1.0,
            "watchlist_cap": 5,
            "min_avg_dollar_volume_30d_usd": 100_000_000,
            "yahoo_batch_size": 10,
            "request_timeout_seconds": 10,
        }
    }
    with (
        patch("src.watchlist_build._download_watchlist_bars", side_effect=fake_download),
        patch("src.watchlist_build.fetch_yahoo_industries", return_value={}),
    ):
        rows = build_rs_technical_watchlist(ranked, config)

    assert len(rows) == 5
    assert rows[0]["symbol"] == "S0"
    assert rows[0]["rs_rank"] == 1


def test_avg_dollar_volume_window() -> None:
    closes = [100.0] * 40
    volumes = [1_000_000.0] * 40
    df = pd.DataFrame({"Close": closes, "Volume": volumes})
    tail = df.tail(AVG_DOLLAR_VOLUME_DAYS)
    avg = (tail["Close"] * tail["Volume"]).mean()
    assert avg == 100.0 * 1_000_000.0
