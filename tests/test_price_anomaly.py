from __future__ import annotations

import unittest

from src.stock_rs import _bars_price_anomaly, _symbol_payload_from_bars


class PriceAnomalyTests(unittest.TestCase):
    def test_spike_isolated(self) -> None:
        bars = [
            {"date": "2026-05-28", "close": 10.0, "volume": 1_000_000},
            {"date": "2026-05-29", "close": 30.0, "volume": 1_000_000},
        ]
        settings = {"max_allowed_daily_return": 1.5, "min_allowed_volume": 1}
        self.assertIsNotNone(_bars_price_anomaly(bars, settings))

    def test_symbol_payload_marks_price_anomaly(self) -> None:
        bars = [
            {"date": "2026-05-28", "close": 5.0, "volume": 500_000},
            {"date": "2026-05-29", "close": 20.0, "volume": 500_000},
        ]
        payload = _symbol_payload_from_bars(
            "TEST",
            bars,
            min_price_rows=2,
            source="yahoo",
            sanity_settings={"max_allowed_daily_return": 1.5, "min_allowed_volume": 1},
        )
        self.assertEqual(payload.get("reason"), "price_anomaly")

    def test_zero_volume_isolated(self) -> None:
        bars = [
            {"date": "2026-05-28", "close": 10.0, "volume": 1_000_000},
            {"date": "2026-05-29", "close": 10.5, "volume": 0},
        ]
        settings = {"max_allowed_daily_return": 1.5, "min_allowed_volume": 1}
        self.assertIsNotNone(_bars_price_anomaly(bars, settings))


if __name__ == "__main__":
    unittest.main()
