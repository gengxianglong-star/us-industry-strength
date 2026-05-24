"""Fetch filtered stock tickers from Finviz screener for an industry."""

from __future__ import annotations

import re
import subprocess
import time
from typing import Any
from urllib.parse import quote

SCREENER_BASE = "https://finviz.com/screener.ashx"
TICKER_PATTERNS = (
    re.compile(r'data-boxover-ticker="([A-Z0-9.-]+)"'),
    re.compile(r'quote\?t=([A-Z0-9.-]+)'),
)
TOTAL_PATTERN = re.compile(r"#\d+\s*/\s*(\d+)\s*Total")
SAVE_PORTFOLIO_PATTERN = re.compile(r"SavePortfolio\((\d+),")
CLOUDFLARE_MARKERS = ("Just a moment...", "cf-browser-verification")


def default_stock_filter_codes(config: dict[str, Any]) -> list[str]:
    stock_filters = config.get("stock_filters", {})
    return [
        stock_filters.get("price_above_sma20", "ta_sma20_pa"),
        stock_filters.get("sma20_above_sma50", "ta_sma50_sb20"),
        stock_filters.get("dollar_volume_min", "sh_curvol_ousd100000"),
    ]


def build_screener_filters(industry_key: str, config: dict[str, Any]) -> str:
    codes = [f"ind_{industry_key}", *default_stock_filter_codes(config)]
    return ",".join(c for c in codes if c)


def build_screener_url(industry_key: str, config: dict[str, Any], start_row: int = 1) -> str:
    filters = build_screener_filters(industry_key, config)
    return f"{SCREENER_BASE}?v=111&f={quote(filters, safe=',')}&r={start_row}"


def _fetch_html(url: str, user_agent: str) -> str:
    """Use curl because Finviz screener often blocks Python requests with Cloudflare."""
    result = subprocess.run(
        [
            "curl",
            "-sL",
            "--max-time",
            "45",
            "-A",
            user_agent,
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"抓取 Finviz screener 失败: {result.stderr.strip() or result.returncode}")
    return result.stdout


def _parse_total(html: str) -> int:
    match = TOTAL_PATTERN.search(html)
    if match:
        return int(match.group(1))
    save_match = SAVE_PORTFOLIO_PATTERN.search(html)
    if save_match:
        return int(save_match.group(1))
    return 0


def _parse_tickers(html: str) -> list[str]:
    if any(marker in html for marker in CLOUDFLARE_MARKERS):
        raise RuntimeError("Finviz screener 被 Cloudflare 拦截，请稍后重试")

    tickers = TICKER_PATTERNS[0].findall(html)
    if not tickers:
        tickers = TICKER_PATTERNS[1].findall(html)

    unique: list[str] = []
    seen: set[str] = set()
    for ticker in tickers:
        if ticker in seen:
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker):
            continue
        seen.add(ticker)
        unique.append(ticker)
    return unique


def fetch_industry_tickers(industry_key: str, config: dict[str, Any]) -> dict[str, Any]:
    scraper = config.get("scraper", {})
    user_agent = scraper.get("user_agent", "Mozilla/5.0")
    delay = float(scraper.get("request_delay_seconds", 1.0))
    per_page = 20

    filters = build_screener_filters(industry_key, config)
    all_tickers: list[str] = []
    start = 1
    total = 0

    while True:
        url = f"{SCREENER_BASE}?v=111&f={quote(filters, safe=',')}&r={start}"
        html = _fetch_html(url, user_agent)
        page_total = _parse_total(html)
        if page_total:
            total = page_total

        page_tickers = _parse_tickers(html)
        if not page_tickers:
            break

        for ticker in page_tickers:
            if ticker not in all_tickers:
                all_tickers.append(ticker)

        if total > 0:
            if start + per_page > total:
                break
        elif len(page_tickers) < per_page:
            break

        start += per_page
        time.sleep(delay)

    return {
        "industry_key": industry_key,
        "tickers": all_tickers,
        "ticker_count": len(all_tickers),
        "screener_url": build_screener_url(industry_key, config, 1),
        "filters": filters,
    }
