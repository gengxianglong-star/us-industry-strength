from __future__ import annotations

import unittest

from src.services.daily_validation import (
    aggregate_overall_status,
    build_step_validations,
    validate_rs_main_step,
)


class DailyValidationTests(unittest.TestCase):
    def test_rs_all_no_bars_fails(self) -> None:
        step = validate_rs_main_step(
            computed_count=0,
            universe_count=7000,
            coverage_ratio=0.0,
            no_bars_count=7000,
        )
        self.assertEqual(step["status"], "failed")

    def test_rs_healthy_passes(self) -> None:
        step = validate_rs_main_step(
            computed_count=6000,
            universe_count=7000,
            coverage_ratio=0.85,
            no_bars_count=100,
        )
        self.assertEqual(step["status"], "done")

    def test_rs_high_no_bars_degraded(self) -> None:
        step = validate_rs_main_step(
            computed_count=5660,
            universe_count=7062,
            coverage_ratio=0.80,
            no_bars_count=1400,
        )
        self.assertEqual(step["status"], "degraded")

    def test_partial_picks_degraded_not_failed(self) -> None:
        pipeline = {
            "industry_count": 144,
            "top_count": 15,
            "stock_pick_errors": 2,
            "picks_summary": {"total": 15, "stale": 1, "with_tickers": 12},
            "rs": {
                "computed_count": 6000,
                "universe_count": 7000,
                "coverage_ratio": 0.85,
                "no_bars_count": 50,
                "watchlist_count": 10,
                "new_stock_leaderboard_count": 5,
            },
            "breadth": {"merged_row_count": 100},
            "breadth_skipped": True,
        }
        config = {"thresholds": {"top_list_count": 10}, "stock_rs": {"new_stock_enabled": True}}

        class _Storage:
            def get_stock_rs_meta(self, _date: str):
                return pipeline["rs"]

            def count_stock_watchlist(self, _date: str) -> int:
                return 10

            def get_breadth_daily(self, limit: int = 1):
                return [{"trade_date": "2026-05-28"}]

        validation = build_step_validations(
            pipeline,
            config=config,
            storage=_Storage(),  # type: ignore[arg-type]
            snapshot_date="2026-05-28",
        )
        self.assertEqual(validation["overall"], "degraded")
        self.assertEqual(aggregate_overall_status(validation["steps"]), "degraded")


if __name__ == "__main__":
    unittest.main()
