from __future__ import annotations

import unittest

from src.services.daily_validation import (
    aggregate_overall_status,
    build_step_validations,
    build_validation_from_storage,
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

    def test_stale_cached_validation_rebuilt_after_rs_done(self) -> None:
        cached = {
            "steps": {
                "industry": {"status": "done"},
                "picks": {"status": "done"},
                "rs_main": {
                    "status": "running",
                    "computed_count": 100,
                    "universe_count": 7000,
                },
                "rs_new": {"status": "skipped"},
                "watchlist": {"status": "degraded"},
                "breadth": {"status": "skipped"},
            },
            "overall": "degraded",
        }

        class _Storage:
            def get_snapshot_run(self, _date: str):
                return {"details": {"validation": cached}, "current_step": "awaiting_rs"}

            def get_latest_rs_job_run(self, _date: str, job_kind: str):
                if job_kind == "main":
                    return {"status": "done"}
                return None

            def get_stock_rs_meta(self, _date: str):
                return {
                    "computed_count": 6000,
                    "universe_count": 7000,
                    "coverage_ratio": 0.85,
                    "no_bars_count": 50,
                    "new_stock_leaderboard_count": 5,
                }

            def get_snapshot(self, _date: str):
                return [{"industry_key": "x"}] * 144

            def get_stock_picks_for_snapshot(self, _date: str):
                return {}

            def count_stock_watchlist(self, _date: str) -> int:
                return 10

            def get_breadth_daily(self, limit: int = 1):
                return [{"trade_date": "2026-05-28"}]

        validation = build_validation_from_storage(
            _Storage(),  # type: ignore[arg-type]
            config={"thresholds": {"top_list_count": 10}, "stock_rs": {"new_stock_enabled": True}},
            snapshot_date="2026-05-28",
        )
        self.assertEqual(validation["steps"]["rs_main"]["status"], "done")
        self.assertIn(validation["overall"], {"ready", "degraded"})


if __name__ == "__main__":
    unittest.main()
