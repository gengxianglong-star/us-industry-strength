"""Tests for industry trajectory export and watchlist rank_w_delta enrichment."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.services.snapshots import build_snapshot_response
from src.storage import Storage


def _insert_snapshot_row(
    storage: Storage,
    snapshot_date: str,
    industry_key: str,
    *,
    rank_w: int,
    rank_m: int,
    rank_q: int,
    rank_h: int = 20,
) -> None:
    with storage._connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshots(snapshot_date, created_at, industry_count) VALUES (?, ?, 1)",
            (snapshot_date, "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "DELETE FROM industry_daily WHERE snapshot_date = ? AND industry_key = ?",
            (snapshot_date, industry_key),
        )
        conn.execute(
            """
            INSERT INTO industry_daily (
                snapshot_date, industry_key, name, stocks,
                perf_w, perf_m, perf_q, perf_h, perf_y,
                rank_w, rank_m, rank_q, rank_h, rank_y,
                score, tier, tags, excluded, exclude_reason, finviz_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_date,
                industry_key,
                industry_key,
                50,
                1.0,
                2.0,
                3.0,
                4.0,
                5.0,
                rank_w,
                rank_m,
                rank_q,
                rank_h,
                80,
                0.7,
                "A",
                json.dumps([]),
                0,
                None,
                "",
            ),
        )
        conn.commit()


class TrajectoryAndRankDeltaTests(unittest.TestCase):
    def test_industry_trajectory_window_chronological(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            for day, rank_m, rank_q in [
                ("2026-05-26", 40, 45),
                ("2026-05-27", 35, 40),
                ("2026-05-28", 30, 35),
            ]:
                _insert_snapshot_row(
                    storage,
                    day,
                    "tech",
                    rank_w=30,
                    rank_m=rank_m,
                    rank_q=rank_q,
                )

            trajectories = storage.get_industry_trajectory_window("2026-05-28", sessions=3)
            trail = trajectories["tech"]
            self.assertEqual(len(trail), 3)
            self.assertEqual(trail[0]["date"], "2026-05-26")
            self.assertEqual(trail[-1]["date"], "2026-05-28")
            self.assertEqual(trail[-1]["rs_1m"], 71.0)
            self.assertEqual(trail[-1]["rs_3m"], 66.0)

    def test_snapshot_response_includes_trajectory_5d(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            for day, rank_m in [("2026-05-27", 40), ("2026-05-28", 30)]:
                _insert_snapshot_row(
                    storage,
                    day,
                    "tech",
                    rank_w=25,
                    rank_m=rank_m,
                    rank_q=35,
                )

            rows = storage.get_snapshot("2026-05-28")
            payload = build_snapshot_response(
                storage=storage,
                snapshot_date="2026-05-28",
                rows=rows,
                top_n=3,
            )
            industry = next(i for i in payload["industries"] if i["industry_key"] == "tech")
            self.assertEqual(len(industry["trajectory_5d"]), 2)

    def test_watchlist_rank_w_delta_positive_when_rank_improves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            for day in [f"2026-05-{d:02d}" for d in range(22, 29)]:
                storage.save_snapshot(day, [])

            for day, rank_w in [("2026-05-23", 80), ("2026-05-28", 60)]:
                storage.save_stock_rs_snapshot(
                    day,
                    [
                        {
                            "symbol": "AAA",
                            "perf_w": 1,
                            "perf_m": 2,
                            "perf_q": 3,
                            "perf_h": 4,
                            "perf_y": 5,
                            "rank_w": rank_w,
                            "rank_m": 50,
                            "rank_q": 50,
                            "rank_h": 50,
                            "rank_y": 50,
                            "rs_score": 0.8,
                            "tier": "A",
                        }
                    ],
                )

            storage.save_stock_watchlist(
                "2026-05-28",
                [{"symbol": "AAA", "rs_score": 0.8, "rs_rank": 1, "industries": ["tech"]}],
            )
            watchlist = storage.get_stock_watchlist("2026-05-28")
            self.assertEqual(len(watchlist), 1)
            self.assertEqual(watchlist[0]["rank_w_delta"], 20)

    def test_new_stock_rows_include_rank_w_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            for day in [f"2026-05-{d:02d}" for d in range(22, 29)]:
                storage.save_snapshot(day, [])

            for day, rank_w in [("2026-05-23", 90), ("2026-05-28", 85)]:
                storage.save_stock_rs_new_snapshot(
                    day,
                    [
                        {
                            "symbol": "IPO",
                            "cohort": "M",
                            "bar_count": 30,
                            "perf_w": 1,
                            "perf_m": 2,
                            "perf_q": 3,
                            "perf_h": 4,
                            "perf_y": 5,
                            "perf_tq": 1.5,
                            "rank_w": rank_w,
                            "rank_m": 40,
                            "rank_q": 45,
                            "rank_h": 50,
                            "rank_y": 55,
                            "rank_tq": 60,
                            "rs_score": 0.6,
                            "tier": "B",
                            "in_leaderboard": 1,
                        }
                    ],
                )

            rows = storage.get_stock_rs_new("2026-05-28", leaderboard_only=True)
            self.assertEqual(rows[0]["rank_w_delta"], 5)


if __name__ == "__main__":
    unittest.main()
