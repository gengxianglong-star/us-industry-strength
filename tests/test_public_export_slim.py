"""Tests for public export row slimming."""

from __future__ import annotations

import unittest

from src.services.public_export import _slim_new_stock_row, _slim_rs_row


class PublicExportSlimTests(unittest.TestCase):
    def test_slim_rs_row_drops_name_and_exchange(self) -> None:
        row = {
            "snapshot_date": "2026-05-29",
            "symbol": "AAPL",
            "rs_score": 0.91,
            "tier": "A",
            "perf_w": 1.2,
            "perf_m": 2.3,
            "perf_q": 3.4,
            "perf_h": 4.5,
            "perf_y": 5.6,
            "rank_w": 10,
            "rank_m": 20,
            "rank_q": 30,
            "rank_h": 40,
            "rank_y": 50,
            "name": "Apple Inc",
            "exchange": "NASDAQ",
        }
        slim = _slim_rs_row(row)
        self.assertEqual(slim["symbol"], "AAPL")
        self.assertEqual(slim["perf_m"], 2.3)
        self.assertNotIn("name", slim)
        self.assertNotIn("exchange", slim)

    def test_slim_new_stock_row_keeps_cohort_fields(self) -> None:
        row = {
            "snapshot_date": "2026-05-29",
            "symbol": "NEW",
            "rs_score": 0.5,
            "tier": "B",
            "cohort": "M",
            "bar_count": 30,
            "perf_tq": 1.1,
            "rank_tq": 99,
            "perf_w": 1.0,
            "perf_m": 2.0,
            "perf_q": 3.0,
            "perf_h": 4.0,
            "perf_y": 5.0,
            "rank_w": 1,
            "rank_m": 2,
            "rank_q": 3,
            "rank_h": 4,
            "rank_y": 5,
            "name": "New Co",
            "exchange": "NYSE",
        }
        slim = _slim_new_stock_row(row)
        self.assertEqual(slim["cohort"], "M")
        self.assertEqual(slim["bar_count"], 30)
        self.assertNotIn("name", slim)


if __name__ == "__main__":
    unittest.main()
