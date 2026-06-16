"""Industry label normalization for Elite ↔ Finviz group matching."""

from __future__ import annotations

from src.stock_picks import _build_elite_industry_index, normalize_industry_label


def test_normalize_industry_label() -> None:
    assert normalize_industry_label("Electronics & Computer Distribution") == (
        "electronics and computer distribution"
    )
    assert normalize_industry_label("REIT - Hotel & Motel") == "reit hotel and motel"


def test_elite_industry_index_uses_normalized_name() -> None:
    market = {
        "ABC": {"industry": "Electronics & Computer Distribution"},
    }
    by_industry = _build_elite_industry_index(market)
    key = normalize_industry_label("Electronics & Computer Distribution")
    assert by_industry.get(key) == ["ABC"]
