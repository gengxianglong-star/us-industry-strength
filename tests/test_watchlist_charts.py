"""Tests for watchlist chart bar export."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.watchlist_charts import (
    _bars_from_dataframe,
    attach_watchlist_chart_bars,
    enrich_watchlist_chart_bars,
    fetch_symbols_bars_yf,
)


def _sample_df(rows: int = 55) -> pd.DataFrame:
    closes = [100.0 + i * 0.2 for i in range(rows)]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Volume": [1_000_000] * rows,
        },
        index=pd.date_range("2026-01-01", periods=rows, freq="B"),
    )


def test_bars_from_dataframe_limits_to_50() -> None:
    bars = _bars_from_dataframe(_sample_df(55))
    assert len(bars) == 50
    assert {"d", "o", "h", "l", "c", "v"} <= set(bars[0].keys())


def test_fetch_symbols_bars_yf_parses_batch() -> None:
    df = _sample_df()
    multi = pd.concat({"AAPL": df, "MSFT": df}, axis=1)

    with patch("src.yfinance_util.yf.download", return_value=multi):
        out = fetch_symbols_bars_yf(["AAPL", "MSFT"])

    assert len(out["AAPL"]) == 50
    assert len(out["MSFT"]) == 50


def test_enrich_refreshes_by_default() -> None:
    stale = [{"d": "2026-01-02", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 1000}]
    row = {"symbol": "AAPL", "chart_bars": stale}
    fresh = [{"d": "2026-03-01", "o": 2, "h": 3, "l": 1.5, "c": 2.5, "v": 2000}] * 12

    with patch("src.watchlist_charts.fetch_symbols_bars_yf", return_value={"AAPL": fresh}):
        out = enrich_watchlist_chart_bars([row])

    assert out[0]["chart_bars"] == fresh


def test_enrich_skips_when_requested() -> None:
    row = {
        "symbol": "AAPL",
        "chart_bars": [
            {"d": f"2026-01-{idx:02d}", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 1000}
            for idx in range(1, 12)
        ],
    }
    with patch("src.watchlist_charts.fetch_symbols_bars_yf") as fetch_mock:
        out = enrich_watchlist_chart_bars([row], skip_if_present=True)
    fetch_mock.assert_not_called()
    assert out[0]["chart_bars"] == row["chart_bars"]


def test_attach_uses_cached_export_when_available() -> None:
    cached = attach_watchlist_chart_bars([{"symbol": "MRVL", "rs_score": 1, "rs_rank": 1}])
    if not cached[0].get("chart_bars"):
        return
    assert len(cached[0]["chart_bars"]) >= 10
