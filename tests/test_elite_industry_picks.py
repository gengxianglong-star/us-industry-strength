"""Elite local industry stock pairing."""

from __future__ import annotations

from src.scoring import ScoredIndustry
from src.stock_picks import build_and_store_elite_industry_picks
from src.storage import Storage


def test_build_and_store_elite_industry_picks(tmp_path) -> None:
    db = tmp_path / "test.db"
    storage = Storage(db)
    snapshot_date = "2026-06-09"
    storage.save_stock_rs_snapshot(
        snapshot_date,
        [
            {
                "symbol": "NVDA",
                "perf_w": 1.0,
                "perf_m": 2.0,
                "perf_q": 3.0,
                "perf_h": 4.0,
                "perf_y": 5.0,
                "rank_w": 1,
                "rank_m": 1,
                "rank_q": 1,
                "rank_h": 1,
                "rank_y": 1,
                "rs_score": 0.99,
                "tier": "A",
            },
            {
                "symbol": "AMD",
                "perf_w": 1.0,
                "perf_m": 2.0,
                "perf_q": 3.0,
                "perf_h": 4.0,
                "perf_y": 5.0,
                "rank_w": 2,
                "rank_m": 2,
                "rank_q": 2,
                "rank_h": 2,
                "rank_y": 2,
                "rs_score": 0.5,
                "tier": "B",
            },
        ],
    )
    scored = [
        ScoredIndustry(
            key="semiconductors",
            name="Semiconductors",
            stocks=100,
            perf_w=1,
            perf_m=2,
            perf_q=3,
            perf_h=4,
            perf_y=5,
            rank_w=1,
            rank_m=1,
            rank_q=1,
            rank_h=1,
            rank_y=1,
            score=0.9,
            tier="A",
            tags=["Core"],
            excluded=False,
        )
    ]
    market = {
        "NVDA": {"industry": "Semiconductors"},
        "AMD": {"industry": "Semiconductors"},
        "AAPL": {"industry": "Consumer Electronics"},
    }
    config = {"thresholds": {"top_list_count": 10}}

    picks = build_and_store_elite_industry_picks(
        storage,
        snapshot_date,
        scored,
        config,
        elite_market=market,
    )

    assert "semiconductors" in picks
    assert picks["semiconductors"]["tickers"] == ["NVDA", "AMD"]
    saved = storage.get_industry_stock_picks(snapshot_date, "semiconductors")
    assert saved is not None
    assert saved["tickers"] == ["NVDA", "AMD"]
