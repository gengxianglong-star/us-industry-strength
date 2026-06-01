from __future__ import annotations

import unittest
from unittest.mock import patch

from src.services.auto_scheduler import AutoScheduler


class AutomationEnsureTests(unittest.TestCase):
    def test_ensure_now_disabled(self) -> None:
        scheduler = AutoScheduler(
            storage=object(),  # type: ignore[arg-type]
            config_getter=lambda: {"automation": {"enabled": False}},
            daily_service=object(),  # type: ignore[arg-type]
        )
        with patch.object(scheduler, "status", return_value={"enabled": False}):
            payload = scheduler.ensure_now(reason="browser")
        self.assertEqual(payload["triggered"], ["disabled"])


if __name__ == "__main__":
    unittest.main()
