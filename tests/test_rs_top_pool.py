"""Tests for RS Top liquid stock pool ranking."""

from __future__ import annotations

from src.config_loader import load_config
from src.services.rs_top_pool import (
    build_rs_top_100_rows,
    is_exchange_traded_fund,
    passes_rs_top_stock_pool_filter,
)


def _market_row(
    *,
    industry: str = "Semiconductors",
    price: str = "100",
    volume: str = "2,000,000",
    perf_w: str = "2%",
    perf_m: str = "5%",
    perf_q: str = "10%",
    perf_h: str = "20%",
    perf_y: str = "50%",
) -> dict[str, str]:
    return {
        "industry": industry,
        "price": price,
        "volume": volume,
        "perf_week": perf_w,
        "perf_month": perf_m,
        "perf_quarter": perf_q,
        "perf_half": perf_h,
        "perf_year": perf_y,
    }


def test_is_exchange_traded_fund() -> None:
    assert is_exchange_traded_fund("Exchange Traded Fund")
    assert not is_exchange_traded_fund("Semiconductors")


def test_passes_rs_top_stock_pool_filter_rejects_etf_and_illiquid() -> None:
    assert passes_rs_top_stock_pool_filter(_market_row())
    assert not passes_rs_top_stock_pool_filter(
        _market_row(industry="Exchange Traded Fund"),
    )
    assert not passes_rs_top_stock_pool_filter(_market_row(price="4.5"))
    assert not passes_rs_top_stock_pool_filter(_market_row(volume="100,000"))


def test_build_rs_top_100_rows_ranks_within_pool_only() -> None:
    config = load_config()
    market = {
        "AAA": _market_row(perf_m="20%", perf_q="30%"),
        "BBB": _market_row(perf_m="5%", perf_q="10%"),
        "MULL": _market_row(
            industry="Exchange Traded Fund",
            perf_m="99%",
            perf_q="99%",
        ),
        "CCC": _market_row(price="3", volume="50,000,000", perf_m="80%", perf_q="80%"),
    }
    rows, meta = build_rs_top_100_rows(config, market, limit=100)
    symbols = [row["symbol"] for row in rows]
    assert meta["pool_count"] == 2
    assert meta["computed_count"] == 2
    assert symbols == ["AAA", "BBB"]
    assert rows[0]["rs_rank"] == 1
    assert rows[0]["rs_score"] > rows[1]["rs_score"]
