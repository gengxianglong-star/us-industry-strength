from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.storage import is_nyse_holiday, latest_trading_date, today_snapshot_date


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

    def test_memorial_day_after_close_rolls_to_prior_friday(self) -> None:
        # 2026-05-25 is Memorial Day (NYSE closed).
        now = datetime(2026, 5, 25, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(latest_trading_date(now), "2026-05-22")
        self.assertTrue(is_nyse_holiday(now.date()))

    def test_day_after_memorial_day_uses_tuesday_session(self) -> None:
        now = datetime(2026, 5, 26, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(latest_trading_date(now), "2026-05-26")

    def test_good_friday_rolls_to_thursday(self) -> None:
        now = datetime(2026, 4, 3, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(latest_trading_date(now), "2026-04-02")
        self.assertTrue(is_nyse_holiday(now.date()))

    def test_independence_day_observed_2026(self) -> None:
        now = datetime(2026, 7, 3, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(latest_trading_date(now), "2026-07-02")


if __name__ == "__main__":
    unittest.main()
