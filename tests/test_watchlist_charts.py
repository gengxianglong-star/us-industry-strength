"""Tests for watchlist chart passthrough (Finviz frontend embed mode)."""

from __future__ import annotations

from src.watchlist_charts import (
    attach_watchlist_chart_bars,
    chart_bar_coverage,
    enrich_watchlist_chart_bars,
)


def test_enrich_passthrough() -> None:
    rows = [{"symbol": "AAPL", "rs_score": 1.0, "rs_rank": 1}]
    assert enrich_watchlist_chart_bars(rows) is rows


def test_attach_passthrough() -> None:
    rows = [{"symbol": "MSFT", "rs_rank": 2}]
    assert attach_watchlist_chart_bars(rows) is rows


def test_chart_bar_coverage_reports_frontend_mode() -> None:
    rows = [{"symbol": "A"}, {"symbol": "B"}]
    assert chart_bar_coverage(rows) == {"total": 2, "with_chart_bars": 0}
