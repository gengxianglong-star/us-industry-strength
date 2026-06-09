"""Fetch filtered stock tickers from Finviz screener for an industry."""

from __future__ import annotations

import http.cookiejar
import re
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
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
SCREENER_BODY_MARKERS = (
    "screener-body",
    "screener_table",
    "is-ticker-cell",
    "screener-export",
)
CLOUDFLARE_MARKERS = (
    "Just a moment...",
    "cf-browser-verification",
    "正在进行安全验证",
    "security verification",
    "challenge-platform",
)

# Core filters always applied (with defaults); growth filters only when set in config.
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


def build_screener_url(industry_key: str, config: dict[str, Any], start_row: int = 1) -> str:
    filters = build_screener_filters(industry_key, config)
    return f"{SCREENER_BASE}?v=111&f={quote(filters, safe=',')}&r={start_row}"


def _is_cloudflare_page(html: str) -> bool:
    lowered = html.lower()
    return any(marker.lower() in lowered for marker in CLOUDFLARE_MARKERS)


def _default_playwright_profile() -> str:
    return str(Path.home() / "Library/Application Support/Microsoft Edge")


def _scraper_settings(config: dict[str, Any]) -> tuple[str, float, str, bool]:
    scraper = config.get("scraper", {})
    user_agent = scraper.get(
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    )
    delay = float(scraper.get("request_delay_seconds", 1.5))
    cookie_file = str(scraper.get("cookie_file") or "").strip()
    prefer_curl = bool(scraper.get("prefer_curl", True))
    return user_agent, delay, cookie_file, prefer_curl


def use_playwright_scraper(config: dict[str, Any]) -> bool:
    return bool(config.get("scraper", {}).get("use_playwright", False))


class PlaywrightFetchSession:
    """Reuse one real browser profile for Finviz screener pages (Cloudflare-safe)."""

    def __init__(self, page: Any) -> None:
        self.page = page

    def fetch_html(self, url: str, *, wait_ms: int = 1200) -> str:
        self.page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        if wait_ms > 0:
            self.page.wait_for_timeout(wait_ms)
        return self.page.content()


@contextmanager
def open_playwright_session(config: dict[str, Any]) -> Iterator[PlaywrightFetchSession]:
    scraper = config.get("scraper", {})
    profile = str(scraper.get("playwright_profile") or _default_playwright_profile()).strip()
    channel = str(scraper.get("playwright_channel") or "msedge").strip()
    headless = bool(scraper.get("playwright_headless", False))
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright 未安装。请运行: pip install playwright && python -m playwright install msedge"
        ) from exc

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            profile,
            channel=channel,
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            yield PlaywrightFetchSession(page)
        finally:
            context.close()


def _load_cookie_jar(cookie_file: str) -> http.cookiejar.MozillaCookieJar | None:
    path = Path(cookie_file)
    if not path.is_file():
        return None
    jar = http.cookiejar.MozillaCookieJar(str(path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except OSError:
        return None
    return jar


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
    jar = _load_cookie_jar(cookie_file)
    if jar is not None:
        session.cookies = jar
    elif cookie_file and Path(cookie_file).is_file():
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


def _is_screener_results_page(html: str) -> bool:
    if _is_cloudflare_page(html):
        return False
    lowered = html.lower()
    if any(marker in lowered for marker in SCREENER_BODY_MARKERS):
        return True
    return bool(TOTAL_PATTERN.search(html) or SAVE_PORTFOLIO_PATTERN.search(html))


def _fetch_html(
    url: str,
    config: dict[str, Any],
    session: requests.Session | None = None,
    playwright_session: PlaywrightFetchSession | None = None,
) -> str:
    if playwright_session is not None:
        html = playwright_session.fetch_html(url)
        if _is_cloudflare_page(html) or not _is_screener_results_page(html):
            raise RuntimeError(
                "Finviz screener 被 Cloudflare 拦截。"
                "请在 Edge 浏览器打开 screener 并完成验证后重试。"
            )
        return html

    user_agent, _, cookie_file, prefer_curl = _scraper_settings(config)
    cloudflare_error = RuntimeError(
        "Finviz screener 被 Cloudflare 拦截。"
        "请在浏览器完成一次验证后，将 Cookie 导出到 config.yaml 的 scraper.cookie_file，"
        "或稍后降低抓取频率再试。"
    )

    def _validate(html: str) -> str:
        if _is_cloudflare_page(html):
            raise cloudflare_error
        return html

    if prefer_curl:
        try:
            return _validate(_fetch_html_with_curl(url, user_agent, cookie_file))
        except (RuntimeError, OSError):
            pass

    html = ""
    try:
        req_session = session or _prepare_session(user_agent, cookie_file)
        html = _validate(_fetch_html_with_requests(req_session, url))
        if _is_screener_results_page(html):
            return html
    except (requests.RequestException, OSError, RuntimeError):
        html = ""

    html = _validate(_fetch_html_with_curl(url, user_agent, cookie_file))
    if not _is_screener_results_page(html):
        raise cloudflare_error
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
    if not _is_screener_results_page(html):
        return []

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
    user_agent, _, cookie_file, _ = _scraper_settings(config)
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
    playwright_session: PlaywrightFetchSession | None = None,
) -> dict[str, Any]:
    user_agent, delay, cookie_file, _ = _scraper_settings(config)
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
        if playwright_session is not None:
            return _fetch_html(url, config, playwright_session=playwright_session)
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
