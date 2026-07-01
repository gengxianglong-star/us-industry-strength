"""Tests for stock-only RS filtering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.storage import Storage


def _seed_rs_row(storage: Storage, snapshot_date: str, symbol: str, rs_score: float) -> None:
    with storage._connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshots(snapshot_date, created_at, industry_count) VALUES (?, ?, 1)",
            (snapshot_date, "2026-07-01T00:00:00+00:00"),
        )
        conn.execute(
            """
            INSERT INTO stock_rs_daily(
                snapshot_date, symbol, perf_w, perf_m, perf_q, perf_h, perf_y,
                rank_w, rank_m, rank_q, rank_h, rank_y, rs_score, tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_date,
                symbol,
                1.0,
                2.0,
                3.0,
                4.0,
                5.0,
                10,
                20,
                30,
                40,
                50,
                rs_score,
                "A",
            ),
        )
        conn.execute(
            """
            INSERT INTO stock_price_daily(symbol, trade_date, close, volume, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (symbol, snapshot_date, 100.0, 2_000_000.0, "test", "2026-07-01T00:00:00+00:00"),
        )
        conn.commit()


class StockRsStocksOnlyTests(unittest.TestCase):
    def test_get_stock_rs_stocks_only_excludes_etf_industry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            snapshot_date = "2026-06-30"
            _seed_rs_row(storage, snapshot_date, "AAPL", 0.95)
            _seed_rs_row(storage, snapshot_date, "MULL", 0.99)
            storage.upsert_stock_universe(
                [
                    {
                        "symbol": "AAPL",
                        "name": "Apple Inc.",
                        "company": "Apple Inc.",
                        "sector": "Technology",
                        "industry": "Consumer Electronics",
                        "exchange": "NASDAQ",
                    },
                    {
                        "symbol": "MULL",
                        "name": "GraniteShares 2x Long MU Daily ETF",
                        "company": "GraniteShares 2x Long MU Daily ETF",
                        "sector": "Financial",
                        "industry": "Exchange Traded Fund",
                        "exchange": "ELITE",
                    },
                ],
                source="elite",
            )

            rows = storage.get_stock_rs(snapshot_date, limit=10, stocks_only=True)

            self.assertEqual([row["symbol"] for row in rows], ["AAPL"])

    def test_get_stock_rs_stocks_only_falls_back_to_legacy_name_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            snapshot_date = "2026-06-30"
            _seed_rs_row(storage, snapshot_date, "SOXL", 0.98)
            with storage._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO stock_universe(
                        symbol, name, company, sector, industry, exchange, source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "SOXL",
                        "Exchange Traded Fund",
                        "",
                        "",
                        "",
                        "ELITE",
                        "legacy",
                        "2026-07-01T00:00:00+00:00",
                    ),
                )
                conn.commit()

            rows = storage.get_stock_rs(snapshot_date, limit=10, stocks_only=True)

            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
