"""Fetch filtered stock tickers from Finviz screener for an industry."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from src.logging_config import get_logger

logger = get_logger(__name__)

SCREENER_BASE = "https://finviz.com/screener.ashx"
FINVIZ_HOME = "https://finviz.com/"
TICKER_PATTERNS = (
    re.compile(r'data-boxover-ticker="([A-Z0-9.-]+)"'),
    re.compile(r'quote\?t=([A-Z0-9.-]+)'),
)
TOTAL_PATTERN = re.compile(r"#\d+\s*/\s*(\d+)\s*Total")
SAVE_PORTFOLIO_PATTERN = re.compile(r"SavePortfolio\((\d+),")
CLOUDFLARE_MARKERS = (
    "Just a moment...",
    "cf-browser-verification",
    "正在进行安全验证",
    "security verification",
    "challenge-platform",
)


def default_stock_filter_codes(config: dict[str, Any]) -> list[str]:
    stock_filters = config.get("stock_filters", {})
    return [
        stock_filters.get("price_above_sma20", "ta_sma20_pa"),
        stock_filters.get("sma20_above_sma50", "ta_sma50_sb20"),
        stock_filters.get("dollar_volume_min", "sh_curvol_ousd100000"),
        stock_filters.get("eps_growth_qoq_min", "fa_epsqoq_o10"),
        stock_filters.get("sales_growth_qoq_min", "fa_salesqoq_o10"),
    ]


def build_screener_filters(industry_key: str, config: dict[str, Any]) -> str:
    codes = [f"ind_{industry_key}", *default_stock_filter_codes(config)]
    return ",".join(c for c in codes if c)


def build_screener_url(industry_key: str, config: dict[str, Any], start_row: int = 1) -> str:
    filters = build_screener_filters(industry_key, config)
    return f"{SCREENER_BASE}?v=111&f={quote(filters, safe=',')}&r={start_row}"


def _is_cloudflare_page(html: str) -> bool:
    lowered = html.lower()
    return any(marker.lower() in lowered for marker in CLOUDFLARE_MARKERS)


def _scraper_settings(config: dict[str, Any]) -> tuple[str, float, str]:
    scraper = config.get("scraper", {})
    user_agent = scraper.get(
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    )
    delay = float(scraper.get("request_delay_seconds", 1.5))
    cookie_file = str(scraper.get("cookie_file") or "").strip()
    return user_agent, delay, cookie_file


def _request_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        "Referer": SCREENER_BASE,
    }


def _prepare_session(user_agent: str, cookie_file: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(_request_headers(user_agent))
    if cookie_file and Path(cookie_file).is_file():
        with Path(cookie_file).open(encoding="utf-8", errors="ignore") as handle:
            session.headers["Cookie"] = handle.read().strip()
    session.get(FINVIZ_HOME, timeout=30)
    time.sleep(0.5)
    session.get(SCREENER_BASE, timeout=30)
    time.sleep(0.5)
    return session


def _fetch_html_with_requests(
    session: requests.Session,
    url: str,
) -> str:
    response = session.get(url, timeout=45)
    response.raise_for_status()
    return response.text


def _fetch_html_with_curl(url: str, user_agent: str, cookie_file: str) -> str:
    cmd = [
        "curl",
        "-sL",
        "--max-time",
        "45",
        "-A",
        user_agent,
        "-e",
        SCREENER_BASE,
    ]
    if cookie_file and Path(cookie_file).is_file():
        cmd.extend(["-b", cookie_file])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"抓取 Finviz screener 失败: {result.stderr.strip() or result.returncode}")
    return result.stdout


def _fetch_html(
    url: str,
    config: dict[str, Any],
    session: requests.Session | None = None,
) -> str:
    user_agent, _, cookie_file = _scraper_settings(config)
    html = ""
    try:
        req_session = session or _prepare_session(user_agent, cookie_file)
        html = _fetch_html_with_requests(req_session, url)
        if not _is_cloudflare_page(html):
            return html
    except (requests.RequestException, OSError):
        html = ""
    html = _fetch_html_with_curl(url, user_agent, cookie_file)
    if _is_cloudflare_page(html):
        raise RuntimeError(
            "Finviz screener 被 Cloudflare 拦截。"
            "请在浏览器完成一次验证后，将 Cookie 导出到 config.yaml 的 scraper.cookie_file，"
            "或稍后降低抓取频率再试。"
        )
    return html


def _parse_total(html: str) -> int:
    match = TOTAL_PATTERN.search(html)
    if match:
        return int(match.group(1))
    save_match = SAVE_PORTFOLIO_PATTERN.search(html)
    if save_match:
        return int(save_match.group(1))
    return 0


def _parse_tickers(html: str) -> list[str]:
    if _is_cloudflare_page(html):
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


def prepare_finviz_session(
    config: dict[str, Any],
) -> tuple[requests.Session | None, threading.Lock]:
    user_agent, _, cookie_file = _scraper_settings(config)
    try:
        return _prepare_session(user_agent, cookie_file), threading.Lock()
    except (requests.RequestException, OSError):
        return None, threading.Lock()


def fetch_industry_tickers(
    industry_key: str,
    config: dict[str, Any],
    *,
    session: requests.Session | None = None,
    session_lock: threading.Lock | None = None,
    skip_warmup: bool = False,
) -> dict[str, Any]:
    user_agent, delay, cookie_file = _scraper_settings(config)
    per_page = 20

    filters = build_screener_filters(industry_key, config)
    all_tickers: list[str] = []
    start = 1
    total = 0
    owns_session = False
    active_session = session
    if active_session is None and not skip_warmup:
        try:
            active_session = _prepare_session(user_agent, cookie_file)
            owns_session = True
        except (requests.RequestException, OSError):
            active_session = None

    def _fetch_page(url: str) -> str:
        if active_session is not None and session_lock is not None:
            with session_lock:
                return _fetch_html(url, config, session=active_session)
        return _fetch_html(url, config, session=active_session)

    request_retries = int(config.get("scraper", {}).get("request_retries", 3))
    request_retries = max(1, min(6, request_retries))
    try:
        while True:
            url = f"{SCREENER_BASE}?v=111&f={quote(filters, safe=',')}&r={start}"
            html = ""
            last_error: Exception | None = None
            for attempt in range(request_retries):
                try:
                    html = _fetch_page(url)
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "finviz screener fetch attempt %d/%d failed: %s",
                        attempt + 1, request_retries, exc,
                    )
                    last_error = exc
                    if owns_session and active_session is not None:
                        try:
                            active_session.close()
                        except Exception:
                            logger.debug("finviz session close failed (ignored)", exc_info=True)
                        active_session = None
                        owns_session = False
                    time.sleep(min(5.0, delay * (attempt + 1)))
            if last_error is not None:
                raise RuntimeError(f"抓取 Finviz screener 失败（重试{request_retries}次）: {last_error}")

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
    finally:
        if owns_session and active_session is not None:
            active_session.close()

    return {
        "industry_key": industry_key,
        "tickers": all_tickers,
        "ticker_count": len(all_tickers),
        "screener_url": build_screener_url(industry_key, config, 1),
        "filters": filters,
    }
