from __future__ import annotations

import unittest
from unittest.mock import patch

from src.services.rs_jobs import RsJobService


class _FakeStorage:
    def get_latest_rs_job_run(self, snapshot_date: str, *, job_kind: str = "main"):
        return {
            "job_id": "main-2026-01-01-abc",
            "status": "running",
            "processed": 5,
            "total": 20,
            "started_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2099-01-01T00:00:00+00:00",
            "result": {},
            "error": None,
        }

    def upsert_rs_job_run(self, *args, **kwargs):
        return None

    def upsert_snapshot_run(self, *args, **kwargs):
        return None


class JobIdempotencyTests(unittest.TestCase):
    def test_rs_start_reuses_running_job(self) -> None:
        service = RsJobService()
        storage = _FakeStorage()
        with patch("src.services.rs_jobs.claim_background_job", return_value=(False, storage.get_latest_rs_job_run("2026-01-01", job_kind="main"))):
            result = service._start_job(  # noqa: SLF001
                storage=storage,
                snapshot_date="2026-01-01",
                job_kind="main",
                run_fn=lambda _: {"attempted_count": 0},
                async_mode=True,
                max_runtime_seconds=60,
            )
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["job_kind"], "main")


if __name__ == "__main__":
    unittest.main()
