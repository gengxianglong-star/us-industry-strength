"""Tests for Finviz Elite export parser."""

from __future__ import annotations

from unittest.mock import patch

from src.services.elite_data import (
    build_elite_export_url,
    build_elite_partial_perf_inputs,
    build_perf_map_from_elite,
    classify_elite_partial_cohort,
    elite_row_for_symbol,
    elite_row_to_perf,
    fetch_elite_market_data,
    parse_finviz_number,
    parse_finviz_percent,
    passes_elite_swing_filters,
    enrich_rs_rows_with_elite_quotes,
    passes_new_stock_screener_filters,
)


def test_fetch_elite_market_data_skips_without_key() -> None:
    assert fetch_elite_market_data(auth_key=None) is None


def test_fetch_elite_market_data_merges_csv() -> None:
    overview = "Ticker,Industry,Sector,Market Cap,Price\nNVDA,Semiconductors,Technology,3.2T,120\n"
    perf = (
        "Ticker,Performance (Week),Performance (Month),Performance (Quarter),"
        "Performance (Half Year),Performance (Year),Relative Volume,"
        "Volatility (Week),Volatility (Month)\n"
        "NVDA,2%,5%,10%,20%,50%,1.5,3%,8%\n"
    )

    technical = "Ticker,SMA20,SMA50,SMA200,Volume\nNVDA,2%,5%,10%,1500000\n"

    with patch(
        "src.services.elite_data._fetch_export_text",
        side_effect=[overview, perf, technical],
    ):
        data = fetch_elite_market_data(auth_key="test-key")

    assert data is not None
    assert data["NVDA"]["industry"] == "Semiconductors"
    assert data["NVDA"]["perf_month"] == "5%"
    assert data["NVDA"]["rel_volume"] == "1.5"
    assert data["NVDA"]["sma20"] == "2%"
    assert data["NVDA"]["volume"] == "1500000"


def test_fetch_elite_market_data_falls_back_on_fetch_error() -> None:
    with patch("src.services.elite_data._fetch_export_text", side_effect=RuntimeError("curl failed")):
        assert fetch_elite_market_data(auth_key="test-key") is None


def test_fetch_elite_market_data_rejects_html_login_page() -> None:
    html = "<!doctype html><html><body>login required</body></html>"
    with patch("src.services.elite_data._fetch_export_text", side_effect=[html, html, html]):
        assert fetch_elite_market_data(auth_key="test-key") is None


def test_build_elite_export_url_uses_elite_host() -> None:
    url = build_elite_export_url(view="111", auth_key="abc", filters="geo_usa")
    assert url.startswith("https://elite.finviz.com/export.ashx")
    assert "f=geo_usa" in url
    assert "auth=abc" in url


def test_parse_finviz_percent() -> None:
    assert parse_finviz_percent("-3.26%") == -3.26
    assert parse_finviz_percent("1.09") == 1.09
    assert parse_finviz_percent("-") is None
    assert parse_finviz_percent("") is None


def test_elite_row_to_perf_requires_all_horizons() -> None:
    row = {
        "perf_week": "2%",
        "perf_month": "5%",
        "perf_quarter": "10%",
        "perf_half": "20%",
        "perf_year": "50%",
    }
    perf = elite_row_to_perf("NVDA", row)
    assert perf == {
        "symbol": "NVDA",
        "perf_w": 2.0,
        "perf_m": 5.0,
        "perf_q": 10.0,
        "perf_h": 20.0,
        "perf_y": 50.0,
    }
    assert elite_row_to_perf("NVDA", {**row, "perf_month": "-"}) is None


def test_elite_row_for_symbol_ticker_aliases() -> None:
    market = {"BRK.B": {"perf_week": "1%"}}
    assert elite_row_for_symbol(market, "BRK-B") == market["BRK.B"]


def test_passes_elite_swing_filters() -> None:
    row = {
        "price": "100",
        "volume": "2,000,000",
        "sma20": "2%",
        "sma50": "5%",
        "sma200": "10%",
    }
    assert passes_elite_swing_filters(row, 0.95)
    assert not passes_elite_swing_filters(row, 0.5)
    assert not passes_elite_swing_filters({**row, "sma200": "-1%"}, 0.95)
    assert not passes_elite_swing_filters({**row, "sma50": "-2%", "sma200": "10%"}, 0.95)
    # Misaligned short-term stack (SMA50 above SMA20) — matches screener ta_sma50_sb20
    assert not passes_elite_swing_filters({**row, "sma50": "1%", "sma20": "3%"}, 0.95)


def test_enrich_rs_rows_with_elite_quotes() -> None:
    rows = [{"symbol": "NVDA", "rs_score": 0.99}]
    market = {"NVDA": {"price": "120", "volume": "2,000,000"}}
    out = enrich_rs_rows_with_elite_quotes(rows, market=market)
    assert out[0]["price"] == 120.0
    assert out[0]["volume"] == 2_000_000.0


def test_enrich_rs_rows_with_elite_quotes_overrides_stale_db_values() -> None:
    rows = [{"symbol": "NVDA", "rs_score": 0.99, "price": 999.0, "volume": 10.0}]
    market = {"NVDA": {"price": "120", "volume": "2,000,000"}}
    out = enrich_rs_rows_with_elite_quotes(rows, market=market)
    assert out[0]["price"] == 120.0
    assert out[0]["volume"] == 2_000_000.0


def test_passes_new_stock_screener_filters() -> None:
    row = {
        "price": "50",
        "volume": "3,000,000",
        "sma20": "2%",
        "sma50": "5%",
    }
    assert passes_new_stock_screener_filters(row)
    assert passes_new_stock_screener_filters(row, min_daily_dollar_volume=100_000_000)
    assert not passes_new_stock_screener_filters(row, min_daily_dollar_volume=200_000_000)
    assert not passes_new_stock_screener_filters({**row, "sma50": "-1%"}, min_daily_dollar_volume=100_000_000)
    assert not passes_new_stock_screener_filters({**row, "sma50": "1%", "sma20": "3%"}, min_daily_dollar_volume=100_000_000)


def test_parse_finviz_number() -> None:
    assert parse_finviz_number("1,500,000") == 1_500_000.0
    assert parse_finviz_number("3.2M") == 3_200_000.0


def test_build_perf_map_from_elite() -> None:
    market = {
        "NVDA": {
            "perf_week": "2%",
            "perf_month": "5%",
            "perf_quarter": "10%",
            "perf_half": "20%",
            "perf_year": "50%",
        },
        "AAPL": {"perf_week": "1%"},  # incomplete
    }
    perf_map, missing = build_perf_map_from_elite(market, ["NVDA", "AAPL", "MSFT"])
    assert list(perf_map.keys()) == ["NVDA"]
    assert set(missing) == {"AAPL", "MSFT"}


def test_classify_elite_partial_m_cohort() -> None:
    row = {
        "perf_week": "5%",
        "perf_month": "12%",
        "perf_quarter": "-",
    }
    hit = classify_elite_partial_cohort(row)
    assert hit is not None
    cohort, perf = hit
    assert cohort == "M"
    assert perf["perf_w"] == 5.0
    assert perf["perf_m"] == 12.0


def test_classify_elite_partial_full_five_returns_none() -> None:
    row = {
        "perf_week": "1%",
        "perf_month": "2%",
        "perf_quarter": "3%",
        "perf_half": "4%",
        "perf_year": "5%",
    }
    assert classify_elite_partial_cohort(row) is None


def test_build_elite_partial_perf_inputs() -> None:
    market = {
        "IPO1": {"perf_week": "2%", "perf_month": "8%", "perf_quarter": "15%"},
        "FULL": {
            "perf_week": "1%",
            "perf_month": "2%",
            "perf_quarter": "3%",
            "perf_half": "4%",
            "perf_year": "5%",
        },
    }
    partial = build_elite_partial_perf_inputs(market, ["IPO1", "FULL", "MISSING"])
    assert "IPO1" in partial
    assert partial["IPO1"][0] == "Q"
    assert "FULL" not in partial
    assert "MISSING" not in partial
