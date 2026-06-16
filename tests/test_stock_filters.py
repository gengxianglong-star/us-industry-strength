"""Tests for Finviz screener filter assembly."""

from __future__ import annotations

import unittest

from src.stock_filters import build_screener_filters, default_stock_filter_codes


class StockFiltersTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
