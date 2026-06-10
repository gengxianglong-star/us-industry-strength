"""Top10 industry rank scan: only industries with RS>=0.9 qualifying picks fill slots."""

from __future__ import annotations

from unittest.mock import patch

from src.config_loader import load_config
from src.scoring import ScoredIndustry, filter_top_strong
from src.stock_picks import build_and_store_elite_industry_picks
from src.stock_rs import rebuild_stock_watchlist_for_snapshot
from src.storage import Storage


def _elite_row() -> dict[str, str]:
    return {
        "price": "100",
        "volume": "2,000,000",
        "sma20": "2%",
        "sma50": "5%",
        "sma200": "10%",
    }


def _rs_row(symbol: str, rs_score: float) -> dict[str, object]:
    return {
        "symbol": symbol,
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
        "rs_score": rs_score,
        "tier": "A",
    }


def _industry(key: str, name: str, score: float) -> ScoredIndustry:
    return ScoredIndustry(
        key=key,
        name=name,
        stocks=20,
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
        score=score,
        tier="A",
        tags=[],
        excluded=False,
    )


def test_top10_skips_empty_industries_and_promotes_lower_ranks(tmp_path) -> None:
    db = tmp_path / "verify.db"
    storage = Storage(db)
    snapshot_date = "2026-06-09"

    scored = [
        _industry("computerhardware", "Computer Hardware", 1.0),
        _industry("empty_a", "Empty A", 0.95),
        _industry("empty_b", "Empty B", 0.90),
        *[
            _industry(f"low_{idx}", f"Low {idx}", 0.85 - idx * 0.01)
            for idx in range(7)
        ],
        _industry("steel", "Steel", 0.50),
        _industry("gold", "Gold", 0.45),
    ]

    rs_rows = [
        _rs_row("SNDK", 0.999),
        _rs_row("STEEL1", 0.995),
        _rs_row("STEEL2", 0.992),
        _rs_row("GOLD1", 0.991),
    ]
    storage.save_stock_rs_snapshot(snapshot_date, rs_rows)
    storage.save_snapshot(snapshot_date, scored)

    market = {
        "SNDK": {**_elite_row(), "industry": "Computer Hardware"},
        "STEEL1": {**_elite_row(), "industry": "Steel"},
        "STEEL2": {**_elite_row(), "industry": "Steel"},
        "GOLD1": {**_elite_row(), "industry": "Gold"},
    }

    def _mock_finviz(industry_key: str, config: dict) -> list[str]:  # noqa: ARG001
        return {"empty_a": ["BAD1"], "empty_b": ["BAD2"]}.get(industry_key, [])

    config = load_config()
    with patch("src.stock_picks._fetch_finviz_industry_candidates", side_effect=_mock_finviz):
        picks = build_and_store_elite_industry_picks(
            storage,
            snapshot_date,
            scored,
            config,
            elite_market=market,
        )

    assert set(picks.keys()) == {"computerhardware", "steel", "gold"}
    assert len(picks["steel"]["tickers"]) == 2
    assert "empty_a" not in picks
    assert "empty_b" not in picks

    top = filter_top_strong(scored, config, stock_picks=picks)
    assert [item.key for item in top] == ["computerhardware", "steel", "gold"]

    info = rebuild_stock_watchlist_for_snapshot(storage, snapshot_date, scored, config)
    assert info["watchlist_count"] >= 1


def test_industry_keeps_all_qualifying_tickers_sorted_by_rs(tmp_path) -> None:
    db = tmp_path / "verify.db"
    storage = Storage(db)
    snapshot_date = "2026-06-09"
    scored = [_industry("semiconductors", "Semiconductors", 1.0)]

    symbols = [("AAA", 0.99), ("BBB", 0.98), ("CCC", 0.97), ("DDD", 0.96), ("EEE", 0.95)]
    storage.save_stock_rs_snapshot(
        snapshot_date,
        [_rs_row(sym, rs) for sym, rs in symbols],
    )
    storage.save_snapshot(snapshot_date, scored)

    market = {
        sym: {**_elite_row(), "industry": "Semiconductors"} for sym, _ in symbols
    }
    config = {
        "thresholds": {"top_list_count": 10},
        "stock_rs": {"cross_top_percent": 0.1, "min_avg_dollar_volume_30d_usd": 100_000_000},
    }

    picks = build_and_store_elite_industry_picks(
        storage,
        snapshot_date,
        scored,
        config,
        elite_market=market,
    )

    assert picks["semiconductors"]["tickers"] == ["AAA", "BBB", "CCC", "DDD", "EEE"]
