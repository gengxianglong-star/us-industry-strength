"""IBD-style composite momentum + percentile RS."""

from __future__ import annotations

import pytest

from src.math_utils import percentile_rank, weighted_momentum_composite
from src.scoring import score_industries
from src.finviz_scraper import IndustryRow
from src.stock_rs import _apply_market_rs_scores


def test_weighted_momentum_composite_uses_config_weights() -> None:
    weights = {
        "week": 0.05,
        "month": 0.30,
        "quarter": 0.40,
        "half": 0.20,
        "year": 0.05,
    }
    row = {
        "perf_w": 1.0,
        "perf_m": 2.0,
        "perf_q": 3.0,
        "perf_h": 4.0,
        "perf_y": 5.0,
    }
    assert weighted_momentum_composite(row, weights) == pytest.approx(2.9)


def test_apply_market_rs_scores_ranks_by_composite() -> None:
    rows = [
        {"symbol": "LOW", "perf_w": 0, "perf_m": 0, "perf_q": 0, "perf_h": 0, "perf_y": 0},
        {"symbol": "HIGH", "perf_w": 10, "perf_m": 10, "perf_q": 10, "perf_h": 10, "perf_y": 10},
    ]
    config = {
        "_normalized_weights": {
            "week": 0.05,
            "month": 0.30,
            "quarter": 0.40,
            "half": 0.20,
            "year": 0.05,
        }
    }
    _apply_market_rs_scores(rows, config, tier_a=0.8, tier_b=0.65)
    high = next(r for r in rows if r["symbol"] == "HIGH")
    low = next(r for r in rows if r["symbol"] == "LOW")
    assert high["rs_score"] == 1.0
    assert low["rs_score"] == 0.0
    assert high["composite_score"] > low["composite_score"]
    assert int(round(high["rs_score"] * 99)) == 99


def test_industry_score_is_weighted_raw_perf() -> None:
    rows = [
        IndustryRow("a", "A", 10, 1, 1, 1, 1, 1, ""),
        IndustryRow("b", "B", 10, 5, 5, 5, 5, 5, ""),
    ]
    config = {
        "weights": {"week": 0.05, "month": 0.3, "quarter": 0.4, "half": 0.2, "year": 0.05},
        "_normalized_weights": {
            "week": 0.05,
            "month": 0.30,
            "quarter": 0.40,
            "half": 0.20,
            "year": 0.05,
        },
        "thresholds": {
            "tier_a_score": 0.8,
            "tier_b_score": 0.65,
            "core_rank_max": 25,
            "max_rank_spread": 60,
            "acceleration_rank_delta": 5,
            "pullback_midterm_rank_max": 30,
            "pullback_week_rank_min": 40,
        },
    }
    scored = score_industries(rows, config)
    a = next(x for x in scored if x.key == "a")
    b = next(x for x in scored if x.key == "b")
    assert b.score > a.score
    assert b.score == weighted_momentum_composite(
        {"perf_w": 5, "perf_m": 5, "perf_q": 5, "perf_h": 5, "perf_y": 5},
        config["_normalized_weights"],
    )
