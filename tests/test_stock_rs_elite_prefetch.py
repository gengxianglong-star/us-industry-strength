"""Elite RS prefetch — skip Yahoo for illiquid/no-perf symbols."""

from __future__ import annotations

from src.stock_rs import _elite_rs_prefetch


def _market_row(**perf: str) -> dict:
    return {
        "perf_week": perf.get("w", "1%"),
        "perf_month": perf.get("m", "2%"),
        "perf_quarter": perf.get("q", "3%"),
        "perf_half": perf.get("h", "4%"),
        "perf_year": perf.get("y", "5%"),
    }


def test_elite_prefetch_skips_yahoo_when_elite_universe() -> None:
    market = {
        "AAPL": _market_row(),
        "DEAD": {"perf_week": "-"},  # no valid perf horizons
    }
    perf_map: dict = {}
    issues_map: dict = {}
    rs_cfg = {"rs_data_provider": "auto"}

    remaining, rs_source, stats = _elite_rs_prefetch(
        ["AAPL", "DEAD"],
        perf_map,
        issues_map,
        rs_cfg,
        prefer_stooq=False,
        elite_market=market,
        skip_yahoo_fallback=True,
    )

    assert remaining == []
    assert rs_source == "elite"
    assert "AAPL" in perf_map
    assert issues_map["DEAD"] == "elite_no_perf"
    assert stats["elite_skipped_yahoo"] == 1
