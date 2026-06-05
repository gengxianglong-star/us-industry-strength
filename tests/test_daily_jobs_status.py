from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.services.daily_jobs import DailyJobService


class DailyJobStatusTests(unittest.TestCase):
    @patch("src.services.daily_jobs.build_validation_from_storage")
    def test_stale_daily_db_job_not_running_forever(self, mock_validation: MagicMock) -> None:
        mock_validation.return_value = {
            "overall": "ready",
            "cockpit_light": "green",
            "headline": "As of 2026-05-28",
            "steps": {},
        }
        storage = MagicMock()
        storage.get_snapshot_run.return_value = None
        storage.get_snapshot.return_value = [{"industry_key": "x"}]
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        storage.get_latest_rs_job_run.return_value = {
            "job_id": "daily-old",
            "status": "running",
            "updated_at": stale_time,
        }

        status = DailyJobService().get_status(
            storage,
            {"thresholds": {"top_list_count": 10}},
            "2026-05-28",
        )
        self.assertNotEqual(status.get("daily_status"), "running")
        self.assertEqual(status.get("daily_status"), "ready")


if __name__ == "__main__":
    unittest.main()
