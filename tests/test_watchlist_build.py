"""Unit tests for RS technical watchlist filters."""

from __future__ import annotations

from src.watchlist_build import (
    avg_dollar_volume,
    filter_rs_technical_candidates,
    passes_technical_momentum_filters,
)


def _bars(
    *,
    closes: list[float],
    volumes: list[float] | None = None,
) -> list[dict]:
    volumes = volumes or [1_000_000] * len(closes)
    return [
        {"date": f"2024-01-{idx + 1:02d}", "close": close, "volume": vol}
        for idx, (close, vol) in enumerate(zip(closes, volumes, strict=False))
    ]


def _uptrend_bars(count: int = 220, *, volume: float = 2_000_000) -> list[dict]:
    closes = [100.0 + i * 0.5 for i in range(count)]
    volumes = [volume] * count
    return _bars(closes=closes, volumes=volumes)


def test_passes_technical_momentum_filters_happy_path() -> None:
    bars = _uptrend_bars()
    assert passes_technical_momentum_filters(bars)


def test_passes_technical_momentum_filters_ignores_volume() -> None:
    bars = _uptrend_bars(volume=10_000)
    assert passes_technical_momentum_filters(bars)


def test_filter_requires_30d_avg_and_caps_at_100() -> None:
    ranked = [{"symbol": f"S{i}", "rs_score": 1.0 - i * 0.001} for i in range(120)]
    bars_by_symbol: dict[str, list] = {}
    for row in ranked:
        symbol = row["symbol"]
        bars_by_symbol[symbol] = _uptrend_bars()

    # Only first 80 symbols meet 30d avg >= 100M
    for idx, symbol in enumerate(bars_by_symbol):
        if idx >= 80:
            bars_by_symbol[symbol] = _bars(
                closes=[200.0 + i for i in range(220)],
                volumes=[100_000.0] * 220,
            )

    out = filter_rs_technical_candidates(
        ranked,
        bars_by_symbol,
        cross_top_percent=1.0,
        cap=100,
        min_avg_30d_dv=100_000_000,
    )
    assert len(out) == 80
    assert out[0]["symbol"] == "S0"


def test_filter_always_applies_30d_avg_even_when_few_candidates() -> None:
    ranked = [
        {"symbol": "HIGH", "rs_score": 0.9},
        {"symbol": "LOW", "rs_score": 0.8},
    ]
    bars_by_symbol = {
        "HIGH": _uptrend_bars(),
        "LOW": _bars(closes=[200.0 + i for i in range(220)], volumes=[100_000.0] * 220),
    }
    out = filter_rs_technical_candidates(
        ranked,
        bars_by_symbol,
        cross_top_percent=1.0,
        cap=100,
        min_avg_30d_dv=100_000_000,
    )
    assert len(out) == 1
    assert out[0]["symbol"] == "HIGH"


def test_filter_takes_top_100_by_rs() -> None:
    ranked = [{"symbol": f"S{i}", "rs_score": float(i)} for i in range(150)]
    ranked.sort(key=lambda x: -x["rs_score"])
    bars_by_symbol = {row["symbol"]: _uptrend_bars() for row in ranked}
    out = filter_rs_technical_candidates(
        ranked,
        bars_by_symbol,
        cross_top_percent=1.0,
        cap=100,
        min_avg_30d_dv=100_000_000,
    )
    assert len(out) == 100
    assert out[0]["symbol"] == "S149"
    assert out[-1]["symbol"] == "S50"


def test_avg_dollar_volume_uses_last_30_sessions() -> None:
    closes = [100.0] * 40
    volumes = [1_000_000.0] * 40
    bars = _bars(closes=closes, volumes=volumes)
    avg = avg_dollar_volume(bars, 30)
    assert avg == 100.0 * 1_000_000.0
