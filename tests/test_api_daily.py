from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.services.daily_jobs import DailyJobService


class DailyApiTests(unittest.TestCase):
    def test_build_dashboard_minimal_shape(self) -> None:
        storage = MagicMock()
        storage.get_snapshot_run.return_value = None
        storage.get_snapshot.return_value = []
        storage.get_breadth_daily.return_value = []
        config = {"thresholds": {"top_list_count": 15}, "stock_rs": {}}
        service = DailyJobService()
        payload = service.build_dashboard(storage, config, "2026-05-28")
        self.assertEqual(payload["display_date"], "2026-05-28")
        self.assertIn("target_date", payload)
        self.assertIn("lag_days", payload)
        self.assertIn("daily_status", payload)
        self.assertIn("environment", payload)
        self.assertIn("top15", payload)

    def test_start_run_skips_ready_without_force(self) -> None:
        service = DailyJobService()
        storage = MagicMock()
        config = {}
        with patch.object(service, "get_status", return_value={"daily_status": "ready"}):
            result = service.start_run(storage, config, "2026-05-28", force=False)
        self.assertEqual(result["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
