"""Contract tests for ranking, scoring tags, and snapshot assembly."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.finviz_scraper import IndustryRow
from src.scoring import filter_top_strong, score_industries, top_strong_sort_key
from src.services.snapshots import build_snapshot_response
from src.storage import Storage


def _test_config(**threshold_overrides: float | int) -> dict:
    thresholds = {
        "tier_a_score": 0.8,
        "tier_b_score": 0.65,
        "core_rank_max": 25,
        "max_rank_spread": 60,
        "top_list_count": 3,
        "acceleration_rank_delta": 5,
        "pullback_midterm_rank_max": 30,
        "pullback_week_rank_min": 40,
    }
    thresholds.update(threshold_overrides)
    return {
        "thresholds": thresholds,
        "_normalized_weights": {
            "week": 0.1,
            "month": 0.25,
            "quarter": 0.35,
            "half": 0.2,
            "year": 0.1,
        },
    }


def _industry_row(
    key: str,
    *,
    perf_w: float,
    perf_m: float,
    perf_q: float,
    perf_h: float,
    perf_y: float,
    name: str | None = None,
) -> IndustryRow:
    return IndustryRow(
        key=key,
        name=name or key,
        stocks=100,
        perf_w=perf_w,
        perf_m=perf_m,
        perf_q=perf_q,
        perf_h=perf_h,
        perf_y=perf_y,
        finviz_url="",
    )


class TopStrongSortKeyTests(unittest.TestCase):
    def test_higher_score_ranks_first(self) -> None:
        high = top_strong_sort_key(0.9, 10, 10, "a")
        low = top_strong_sort_key(0.8, 5, 5, "b")
        self.assertLess(high, low)

    def test_tie_break_by_month_then_quarter_rank(self) -> None:
        better_month = top_strong_sort_key(0.85, 5, 20, "a")
        worse_month = top_strong_sort_key(0.85, 15, 5, "b")
        self.assertLess(better_month, worse_month)


class ScoringTagTests(unittest.TestCase):
    def test_acceleration_tag_requires_rank_delta(self) -> None:
        rows = [
            _industry_row(
                f"f{i}",
                perf_w=float(i),
                perf_m=float(i),
                perf_q=float(i),
                perf_h=float(i),
                perf_y=float(i),
            )
            for i in range(20)
        ]
        rows.append(
            _industry_row(
                "accel",
                perf_w=100.0,
                perf_m=13.0,
                perf_q=5.0,
                perf_h=12.0,
                perf_y=11.0,
            )
        )
        scored = score_industries(rows, _test_config(acceleration_rank_delta=5))
        accel = next(x for x in scored if x.key == "accel")
        self.assertIn("Accel↑", accel.tags)

    def test_pullback_tag_on_strong_midterm_week_weakness(self) -> None:
        rows = [
            _industry_row(
                f"f{i}",
                perf_w=float(i),
                perf_m=float(i),
                perf_q=float(i),
                perf_h=float(i),
                perf_y=float(i),
            )
            for i in range(50)
        ]
        rows.append(
            _industry_row(
                "pullback",
                perf_w=-50.0,
                perf_m=200.0,
                perf_q=190.0,
                perf_h=180.0,
                perf_y=170.0,
            )
        )
        scored = score_industries(rows, _test_config())
        item = next(x for x in scored if x.key == "pullback")
        self.assertIn("Strong PB", item.tags)


class SnapshotStaleFallbackTests(unittest.TestCase):
    def test_stock_picks_stale_fallback_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            snapshot_date = "2026-05-26"
            scored_rows = score_industries(
                [
                    _industry_row(
                        "semis",
                        perf_w=1.0,
                        perf_m=2.0,
                        perf_q=3.0,
                        perf_h=4.0,
                        perf_y=5.0,
                        name="Semis",
                    )
                ],
                _test_config(),
            )
            storage.save_snapshot(snapshot_date, scored_rows)
            storage.save_industry_stock_picks(
                snapshot_date,
                "semis",
                ["AXTI", "NVDA"],
                screener_url="https://example.com",
                filters="",
                error="沿用缓存(2026-05-25): SSL EOF",
            )

            payload = build_snapshot_response(
                storage=storage,
                snapshot_date=snapshot_date,
                rows=storage.get_snapshot(snapshot_date),
                top_n=10,
            )
            industry = payload["industries"][0]
            self.assertTrue(industry["stock_picks_stale_fallback"])
            self.assertEqual(industry["stock_picks"], ["AXTI", "NVDA"])


class FilterTopStrongTests(unittest.TestCase):
    def test_respects_top_list_count(self) -> None:
        rows = [
            _industry_row(f"i{n}", perf_w=n, perf_m=n, perf_q=n, perf_h=n, perf_y=n)
            for n in range(5)
        ]
        scored = score_industries(rows, _test_config(top_list_count=2))
        top = filter_top_strong(scored, _test_config(top_list_count=2))
        self.assertEqual(len(top), 2)


if __name__ == "__main__":
    unittest.main()
