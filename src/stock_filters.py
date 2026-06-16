"""Finviz screener filter codes for Elite industry export (f= parameter)."""

from __future__ import annotations

from typing import Any

CORE_STOCK_FILTER_KEYS: tuple[str, ...] = (
    "price_above_sma20",
    "sma20_above_sma50",
    "price_above_sma200",
    "dollar_volume_min",
)
OPTIONAL_STOCK_FILTER_KEYS: tuple[str, ...] = (
    "eps_growth_qoq_min",
    "sales_growth_qoq_min",
)
STOCK_FILTER_DEFAULTS: dict[str, str] = {
    "price_above_sma20": "ta_sma20_pa",
    "sma20_above_sma50": "ta_sma50_sb20",
    "price_above_sma200": "ta_sma200_pa",
    "dollar_volume_min": "sh_curvol_ousd100M",
    "eps_growth_qoq_min": "fa_epsqoq_o10",
    "sales_growth_qoq_min": "fa_salesqoq_o10",
}


def default_stock_filter_codes(config: dict[str, Any]) -> list[str]:
    stock_filters = config.get("stock_filters", {})
    codes: list[str] = []
    for key in CORE_STOCK_FILTER_KEYS:
        code = str(stock_filters.get(key) or STOCK_FILTER_DEFAULTS[key]).strip()
        if code:
            codes.append(code)
    for key in OPTIONAL_STOCK_FILTER_KEYS:
        if key not in stock_filters:
            continue
        code = str(stock_filters.get(key) or "").strip()
        if code:
            codes.append(code)
    return codes


def build_screener_filters(industry_key: str, config: dict[str, Any]) -> str:
    codes = [f"ind_{industry_key}", *default_stock_filter_codes(config)]
    return ",".join(c for c in codes if c)
