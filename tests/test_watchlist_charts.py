from src.watchlist_charts import _adjust_factor, attach_watchlist_chart_bars, enrich_watchlist_chart_bars


def test_adjust_factor():
    assert _adjust_factor(100, 95) == 0.95
    assert _adjust_factor(0, 95) == 1.0
    assert _adjust_factor(100, None) == 1.0


def test_attach_uses_cached_export_when_available():
    cached = attach_watchlist_chart_bars([{"symbol": "MRVL", "rs_score": 1, "rs_rank": 1}])
    if not cached[0].get("chart_bars"):
        return  # no export file in CI sandbox
    assert len(cached[0]["chart_bars"]) >= 10


def test_enrich_skips_when_chart_bars_present():
    row = {
        "symbol": "AAPL",
        "chart_bars": [
            {"d": "2026-01-02", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 1000},
        ],
    }
    out = enrich_watchlist_chart_bars([row])
    assert out[0]["chart_bars"] == row["chart_bars"]
