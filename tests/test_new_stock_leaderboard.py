"""New-stock leaderboard: full-universe top10% ∩ partial-perf cohort."""

from __future__ import annotations

from src.scoring import ScoredIndustry
from src.stock_rs import _build_new_stock_watchlist_candidates, compute_and_store_new_stock_rs
from src.storage import Storage


def _market() -> dict[str, dict]:
    """5 mature + 3 partial (M-cohort) symbols."""
    mature = {
        sym: {
            "perf_week": "1%",
            "perf_month": "2%",
            "perf_quarter": "3%",
            "perf_half": "4%",
            "perf_year": "5%",
        }
        for sym in ("OLD1", "OLD2", "OLD3", "OLD4", "OLD5")
    }
    # IPOs: only week+month -> M cohort; give them best month perf
    new_stocks = {
        "IPO1": {"perf_week": "20%", "perf_month": "50%", "perf_quarter": "-", "perf_half": "-", "perf_year": "-"},
        "IPO2": {"perf_week": "15%", "perf_month": "40%", "perf_quarter": "-", "perf_half": "-", "perf_year": "-"},
        "IPO3": {"perf_week": "1%", "perf_month": "2%", "perf_quarter": "-", "perf_half": "-", "perf_year": "-"},
    }
    return {**mature, **new_stocks}


def test_new_stock_leaderboard_full_universe_top_slice(tmp_path) -> None:
    storage = Storage(tmp_path / "t.db")
    snapshot_date = "2026-06-16"
    market = _market()
    config = {"stock_rs": {"new_stock_enabled": True, "tier_a_score": 0.8, "tier_b_score": 0.65}}
    scored = [
        ScoredIndustry(
            key="semis",
            name="Semis",
            stocks=10,
            perf_w=1,
            perf_m=1,
            perf_q=1,
            perf_h=1,
            perf_y=1,
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
    ]
    storage.save_industry_stock_picks(snapshot_date, "semis", ["IPO1", "IPO2", "IPO3"], "", "")

    out = compute_and_store_new_stock_rs(
        storage,
        snapshot_date,
        config,
        cross_top_percent=0.5,
        scored_industries=scored,
        elite_market=market,
    )

    # Universe for M = 8 symbols (all have week+month); top 50% = 4 slots
    # Leaderboard = new stocks in top 4: IPO1, IPO2 likely; IPO3 maybe not
    lb = [r for r in out["new_stock_rows"] if r.get("in_leaderboard")]
    lb_syms = {r["symbol"] for r in lb}
    assert "IPO1" in lb_syms
    assert out["new_stock_m_count"] == 3
    assert out["new_stock_leaderboard_count"] == len(lb)
    assert out["new_stock_leaderboard_count"] < out["new_stock_m_count"]


def test_new_stock_watchlist_relaxed_screener_and_industry() -> None:
    scored = [
        ScoredIndustry(
            key="semis",
            name="Semiconductors",
            stocks=10,
            perf_w=1,
            perf_m=1,
            perf_q=1,
            perf_h=1,
            perf_y=1,
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
    ]
    market = {
        "IPO1": {
            "industry": "Semiconductors",
            "price": "100",
            "volume": "2,000,000",
            "sma20": "2%",
            "sma50": "5%",
        },
        "IPO2": {
            "industry": "Semiconductors",
            "price": "10",
            "volume": "1,000,000",
            "sma20": "2%",
            "sma50": "5%",
        },
    }
    leaderboard = [
        {"symbol": "IPO1", "rs_score": 0.95},
        {"symbol": "IPO2", "rs_score": 0.9},
    ]
    config = {"thresholds": {"top_list_count": 10}, "stock_rs": {}}
    out = _build_new_stock_watchlist_candidates(
        leaderboard,
        market=market,
        scored_industries=scored,
        config=config,
    )
    assert [r["symbol"] for r in out] == ["IPO1"]
