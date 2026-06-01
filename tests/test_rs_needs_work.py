from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.services.auto_scheduler import AutoScheduler


class RsNeedsWorkTests(unittest.TestCase):
    def test_high_no_bars_triggers_recovery(self) -> None:
        storage = MagicMock()
        storage.get_snapshot.return_value = [{"symbol": "AAPL"}]
        storage.get_latest_rs_job_run.return_value = {"status": "done"}
        storage.get_stock_rs_meta.return_value = {
            "computed_count": 5660,
            "coverage_ratio": 0.80,
            "no_bars_count": 1400,
            "universe_count": 7062,
        }
        scheduler = AutoScheduler(
            storage=storage,
            config_getter=lambda: {"automation": {"enabled": True}},
            daily_service=MagicMock(),
        )
        self.assertTrue(scheduler._rs_needs_work("2026-05-29"))

    def test_normal_no_bars_skips_recovery(self) -> None:
        storage = MagicMock()
        storage.get_snapshot.return_value = [{"symbol": "AAPL"}]
        storage.get_latest_rs_job_run.return_value = {"status": "done"}
        storage.get_stock_rs_meta.return_value = {
            "computed_count": 5660,
            "coverage_ratio": 0.80,
            "no_bars_count": 154,
            "universe_count": 7062,
        }
        scheduler = AutoScheduler(
            storage=storage,
            config_getter=lambda: {"automation": {"enabled": True}},
            daily_service=MagicMock(),
        )
        self.assertFalse(scheduler._rs_needs_work("2026-05-29"))


if __name__ == "__main__":
    unittest.main()
