from __future__ import annotations

import unittest
from unittest.mock import patch

from src.server import api_health


class HealthApiTests(unittest.TestCase):
    def test_health_endpoint_returns_report(self) -> None:
        fake = {
            "status": "ok",
            "server_time": "2026-01-01T00:00:00+00:00",
            "checks": {
                "db": {"ok": True, "latency_ms": 1, "detail": ""},
                "proxy": {"ok": True, "latency_ms": 1, "detail": ""},
                "finviz": {"ok": True, "latency_ms": 1, "detail": ""},
                "breadth_source": {"ok": True, "latency_ms": 1, "detail": ""},
            },
        }
        with patch("src.server.build_health_report", return_value=fake):
            payload = api_health()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("checks", payload)


if __name__ == "__main__":
    unittest.main()
