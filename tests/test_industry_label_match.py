"""Industry label normalization for Elite ↔ Finviz group matching."""

from __future__ import annotations

from src.scoring import ScoredIndustry
from src.stock_picks import (
    _build_elite_industry_index,
    _lookup_elite_candidates,
    normalize_industry_label,
)


def test_normalize_industry_label() -> None:
    assert normalize_industry_label("Electronics & Computer Distribution") == (
        "electronics and computer distribution"
    )
    assert normalize_industry_label("REIT - Hotel & Motel") == "reit hotel and motel"


def test_lookup_elite_candidates_uses_normalized_name() -> None:
    market = {
        "ABC": {"industry": "Electronics & Computer Distribution"},
    }
    by_industry = _build_elite_industry_index(market)
    item = ScoredIndustry(
        key="electronicscomputerdistribution",
        name="Electronics & Computer Distribution",
        stocks=8,
        perf_w=0,
        perf_m=0,
        perf_q=0,
        perf_h=0,
        perf_y=0,
        rank_w=1,
        rank_m=1,
        rank_q=1,
        rank_h=1,
        rank_y=1,
        score=1.0,
        tier="A",
        tags=[],
        excluded=False,
    )
    assert _lookup_elite_candidates(item, by_industry) == ["ABC"]
