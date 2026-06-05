from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.services.auto_scheduler import AutoScheduler, automation_settings


class AutoSchedulerTests(unittest.TestCase):
    def test_settings_defaults(self) -> None:
        cfg = automation_settings({})
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["daily_hour"], 6)
        self.assertTrue(cfg["retry_failed"])

    @patch("src.services.auto_scheduler.latest_trading_date", return_value="2026-05-29")
    def test_ensure_daily_skips_when_ready(self, _mock_trade_date: MagicMock) -> None:
        daily = MagicMock()
        daily.get_status.return_value = {"daily_status": "ready"}
        daily.start_run.return_value = {"status": "skipped"}
        storage = MagicMock()
        storage.get_latest_date.return_value = "2026-05-29"
        storage.get_snapshot.return_value = [{"industry_key": "x"}]
        scheduler = AutoScheduler(
            storage=storage,
            config_getter=lambda: {"automation": {"enabled": True}},
            daily_service=daily,
            rs_service=MagicMock(),
        )
        scheduler._ensure_daily(reason="startup")
        daily.start_run.assert_not_called()

    @patch("src.services.auto_scheduler._save_state")
    def test_ensure_daily_forces_when_lagging(self, save_state: MagicMock) -> None:
        daily = MagicMock()
        daily.get_status.return_value = {"daily_status": "idle"}
        daily.start_run.return_value = {"status": "started"}
        storage = MagicMock()
        storage.get_latest_date.return_value = "2026-05-28"
        storage.get_snapshot.return_value = None
        scheduler = AutoScheduler(
            storage=storage,
            config_getter=lambda: {"automation": {"enabled": True}},
            daily_service=daily,
            rs_service=MagicMock(),
        )
        scheduler._ensure_daily(reason="catchup", force_catchup=True)
        daily.start_run.assert_called_once()
        self.assertTrue(daily.start_run.call_args.kwargs.get("force"))
        save_state.assert_called_once()

    def test_ensure_breadth_when_lagging(self) -> None:
        breadth = MagicMock()
        breadth.get_state.return_value = {"status": "idle"}
        breadth.start_sync.return_value = {"status": "started"}
        storage = MagicMock()
        storage.get_breadth_daily.return_value = [{"trade_date": "2026-05-27"}]
        storage.get_latest_rs_job_run.return_value = None
        scheduler = AutoScheduler(
            storage=storage,
            config_getter=lambda: {"automation": {"enabled": True, "daily": {"skip_breadth": False}}},
            daily_service=MagicMock(),
            rs_service=MagicMock(),
            breadth_service=breadth,
        )
        with patch("src.services.auto_scheduler._save_state"):
            scheduler._ensure_breadth_if_needed("2026-05-29")
        breadth.start_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
