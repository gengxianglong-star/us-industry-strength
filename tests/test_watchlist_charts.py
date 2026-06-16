"""Tests for watchlist chart bar attachment."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.watchlist_charts import (
    attach_watchlist_chart_bars,
    chart_bar_coverage,
    enrich_watchlist_chart_bars,
)


def _sample_df() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    return pd.DataFrame(
        {
            "Open": [100 + i * 0.1 for i in range(30)],
            "High": [101 + i * 0.1 for i in range(30)],
            "Low": [99 + i * 0.1 for i in range(30)],
            "Close": [100.5 + i * 0.1 for i in range(30)],
        },
        index=idx,
    )


class WatchlistChartTests(unittest.TestCase):
    def test_enrich_attaches_chart_bars(self) -> None:
        rows = [{"symbol": "AAPL", "rs_score": 0.9}]
        frames = {"AAPL": _sample_df()}
        with patch("src.watchlist_charts.download_ticker_frames", return_value=frames):
            out = enrich_watchlist_chart_bars(rows)
        self.assertGreaterEqual(len(out[0].get("chart_bars") or []), 10)

    def test_attach_passthrough_when_download_empty(self) -> None:
        rows = [{"symbol": "ZZZ", "rs_score": 0.5}]
        with patch("src.watchlist_charts.download_ticker_frames", return_value={}):
            out = attach_watchlist_chart_bars(rows)
        self.assertEqual(out, rows)

    def test_chart_bar_coverage_counts_rows(self) -> None:
        rows = [
            {"symbol": "A", "chart_bars": [{"d": "2026-01-01", "o": 1, "h": 2, "l": 1, "c": 2}] * 12},
            {"symbol": "B"},
        ]
        self.assertEqual(chart_bar_coverage(rows), {"total": 2, "with_chart_bars": 1})


if __name__ == "__main__":
    unittest.main()
