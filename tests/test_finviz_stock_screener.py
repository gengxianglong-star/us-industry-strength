"""Tests for Finviz industry stock screener filter assembly."""

from __future__ import annotations

import unittest

from src.finviz_stock_screener import (
    _is_screener_results_page,
    build_screener_filters,
    default_stock_filter_codes,
)


class FinvizStockScreenerTests(unittest.TestCase):
    def test_default_filters_include_dollar_volume_100m(self) -> None:
        config = {"stock_filters": {}}
        codes = default_stock_filter_codes(config)
        self.assertIn("sh_curvol_ousd100M", codes)

    def test_build_screener_filters_applies_configured_volume(self) -> None:
        config = {
            "stock_filters": {
                "dollar_volume_min": "sh_curvol_ousd100M",
                "price_above_sma200": "ta_sma200_pa",
            }
        }
        filters = build_screener_filters("semiconductors", config)
        self.assertTrue(filters.startswith("ind_semiconductors,"))
        self.assertIn("sh_curvol_ousd100M", filters)
        self.assertIn("ta_sma200_pa", filters)

    def test_optional_growth_filters_omitted_when_blank(self) -> None:
        config = {
            "stock_filters": {
                "dollar_volume_min": "sh_curvol_ousd100M",
                "eps_growth_qoq_min": "",
                "sales_growth_qoq_min": "",
            }
        }
        filters = build_screener_filters("steel", config)
        self.assertNotIn("fa_epsqoq_o10", filters)
        self.assertNotIn("fa_salesqoq_o10", filters)

    def test_screener_page_detection_rejects_cloudflare(self) -> None:
        html = "<html><title>Just a moment...</title><body>challenge-platform</body></html>"
        self.assertFalse(_is_screener_results_page(html))

    def test_screener_page_detection_accepts_results_table(self) -> None:
        html = '<div class="screener-body">#1 / 12 Total</div>'
        self.assertTrue(_is_screener_results_page(html))


if __name__ == "__main__":
    unittest.main()
