from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.storage import latest_trading_date, today_snapshot_date


class TradingDateTests(unittest.TestCase):
    def test_saturday_uses_previous_friday(self) -> None:
        # 2026-05-30 is Saturday in New York.
        now = datetime(2026, 5, 30, 15, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(latest_trading_date(now), "2026-05-29")
        self.assertEqual(today_snapshot_date(now), "2026-05-30")

    def test_weekday_before_close_uses_previous_session(self) -> None:
        now = datetime(2026, 5, 29, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(latest_trading_date(now), "2026-05-28")

    def test_weekday_after_close_uses_same_day(self) -> None:
        now = datetime(2026, 5, 29, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(latest_trading_date(now), "2026-05-29")


if __name__ == "__main__":
    unittest.main()
