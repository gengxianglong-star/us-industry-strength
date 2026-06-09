"""Fetch and parse Finviz Industry group data (no Elite required)."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.logging_config import get_logger
from src.proxy_util import resolve_proxy_url

logger = get_logger(__name__)

OVERVIEW_URL = "https://finviz.com/groups.ashx?g=industry&o=name&v=110"
PERFORMANCE_URL = "https://finviz.com/groups.ashx?g=industry&o=-perf1m&v=142"
FINVIZ_HOME = "https://finviz.com/"

INDUSTRY_KEY_RE = re.compile(r"f=ind_([^\"&]+)")

CLOUDFLARE_MARKERS = [
    "Just a moment...",
    "cf-browser-verification",
    "cf-challenge",
    "cf-browser-verify",
    "challenge-platform",
    "Checking your browser",
    "captcha-bypass",
    "正在进行安全验证",
    "security verification",
]


@dataclass
class IndustryRow:
    key: str
    name: str
    stocks: int
    perf_w: float
    perf_m: float
    perf_q: float
    perf_h: float
    perf_y: float
    finviz_url: str


def _parse_percent(text: str) -> float:
    cleaned = text.strip().replace("%", "").replace(",", "")
    if not cleaned or cleaned == "-":
        return 0.0
    return float(cleaned)


def _extract_key(link: str) -> str | None:
    match = INDUSTRY_KEY_RE.search(link)
    return match.group(1) if match else None


def _is_cloudflare_page(html: str) -> bool:
    lowered = html.lower()
    return any(marker.lower() in lowered for marker in CLOUDFLARE_MARKERS)


def _stale_fallback_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("scraper", {}).get("stale_fallback_enabled", True))


def _scraper_settings(config: dict[str, Any]) -> tuple[str, float, str, bool]:
    scraper = config.get("scraper", {})
    user_agent = scraper.get(
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    )
    delay = float(scraper.get("request_delay_seconds", 1.0))
    cookie_file = str(scraper.get("cookie_file") or "").strip()
    prefer_curl = bool(scraper.get("prefer_curl", True))
    return user_agent, delay, cookie_file, prefer_curl


def _fetch_text_with_requests(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=45)
    response.raise_for_status()
    return response.text


def _fetch_text_with_curl(url: str, config: dict[str, Any]) -> str:
    scraper = config.get("scraper", {})
    user_agent = scraper.get(
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    )
    cookie_file = str(scraper.get("cookie_file") or "").strip()
    use_system_proxy = bool(scraper.get("use_system_proxy", True))
    proxy_url = str(scraper.get("proxy_url") or "").strip()
    proxy, _ = resolve_proxy_url(explicit=proxy_url, use_system_proxy=use_system_proxy)

    cmd = [
        "curl",
        "-sL",
        "--max-time",
        "45",
        "--retry",
        "2",
        "--retry-delay",
        "1",
        "--retry-all-errors",
        "--compressed",
        "-A",
        user_agent,
        "-e",
        FINVIZ_HOME,
        "-H",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    ]
    if proxy:
        cmd.extend(["-x", proxy])
    if cookie_file and Path(cookie_file).is_file():
        cmd.extend(["-b", cookie_file])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"curl 抓取 Finviz 失败: {result.stderr.strip() or result.returncode}")
    if not result.stdout.strip():
        raise RuntimeError("curl 抓取 Finviz 返回空内容")
    return result.stdout


def _prepare_session(user_agent: str, cookie_file: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        "Referer": FINVIZ_HOME,
    })
    if cookie_file and Path(cookie_file).is_file():
        with Path(cookie_file).open(encoding="utf-8", errors="ignore") as handle:
            session.headers["Cookie"] = handle.read().strip()
    try:
        session.get(FINVIZ_HOME, timeout=30)
        time.sleep(0.5)
    except requests.RequestException as exc:
        logger.debug("finviz home warmup skipped: %s", exc)
    return session


def _validate_industry_html(html: str, url: str) -> str:
    if _is_cloudflare_page(html):
        raise RuntimeError(f"Finviz 返回 Cloudflare 验证页面 ({url})")
    if "Name" not in html:
        raise RuntimeError(f"Finviz 页面缺少行业表 ({url})")
    return html


def _fetch_html_with_retry(
    url: str,
    config: dict[str, Any],
    session: requests.Session | None = None,
    max_retries: int = 3,
) -> str:
    """Fetch HTML with curl-first option, requests retry, and curl fallback."""
    user_agent, delay, cookie_file, prefer_curl = _scraper_settings(config)
    last_error: Exception | None = None

    for attempt in range(max_retries):
        # 尝试 1: 如果配置了优先使用 curl，先用 curl 试
        if prefer_curl:
            try:
                return _validate_industry_html(_fetch_text_with_curl(url, config), url)
            except (OSError, RuntimeError) as exc:
                last_error = exc
                logger.debug("finviz curl attempt %d failed: %s", attempt + 1, exc)

        # 尝试 2: 使用常规的 requests
        try:
            if session is None:
                session = _prepare_session(user_agent, cookie_file)
            return _validate_industry_html(_fetch_text_with_requests(session, url), url)
        except (requests.RequestException, OSError, RuntimeError) as exc:
            last_error = exc
            logger.debug("finviz requests attempt %d failed: %s", attempt + 1, exc)

        # 尝试 3: 只有在前面没有优先用过 curl 的情况下，作为最后手段用 curl 试一次
        if not prefer_curl:
            try:
                return _validate_industry_html(_fetch_text_with_curl(url, config), url)
            except (OSError, RuntimeError) as curl_exc:
                last_error = curl_exc

        # 如果都失败了，喝口水休息一下，准备下一轮大循环重试
        if attempt < max_retries - 1:
            time.sleep(delay * (attempt + 1))  # 动态增加等待时间 (1秒, 2秒...)
            session = None

    raise RuntimeError(f"无法抓取 Finviz 页面 ({url}): {last_error}")


def _fetch_html(url: str, config: dict[str, Any]) -> str:
    """Simple wrapper — kept for backward compatibility."""
    return _fetch_html_with_retry(url, config)


def _find_data_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Name" in headers:
            return table, headers
    raise ValueError("无法在 Finviz 页面中找到行业数据表")


def parse_overview(html: str) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table, headers = _find_data_table(soup)
    name_idx = headers.index("Name")
    stocks_idx = headers.index("Stocks")

    overview: dict[str, dict[str, Any]] = {}
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) <= max(name_idx, stocks_idx):
            continue
        link = tds[name_idx].find("a")
        if not link:
            continue
        href = link.get("href", "")
        key = _extract_key(href)
        if not key:
            continue
        overview[key] = {
            "name": link.get_text(strip=True),
            "stocks": int(tds[stocks_idx].get_text(strip=True).replace(",", "")),
            "finviz_url": f"https://finviz.com/screener?f=ind_{key}&v=141",
        }
    return overview


def parse_performance(html: str) -> dict[str, dict[str, float]]:
    soup = BeautifulSoup(html, "html.parser")
    table, headers = _find_data_table(soup)
    name_idx = headers.index("Name")
    perf_map = {
        "week": headers.index("Perf Week"),
        "month": headers.index("Perf Month"),
        "quarter": headers.index("Perf Quart"),
        "half": headers.index("Perf Half"),
        "year": headers.index("Perf Year"),
    }

    performance: dict[str, dict[str, float]] = {}
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) <= name_idx:
            continue
        link = tds[name_idx].find("a")
        if not link:
            continue
        key = _extract_key(link.get("href", ""))
        if not key:
            continue
        performance[key] = {
            tf: _parse_percent(tds[idx].get_text(strip=True))
            for tf, idx in perf_map.items()
        }
    return performance


def _fetch_industries_live(config: dict[str, Any]) -> list[IndustryRow]:
    scraper = config.get("scraper", {})
    delay = float(scraper.get("request_delay_seconds", 1.0))
    retries = int(scraper.get("request_retries", 3))

    session = None
    overview_html = _fetch_html_with_retry(OVERVIEW_URL, config, session, max_retries=retries)
    time.sleep(delay)
    performance_html = _fetch_html_with_retry(PERFORMANCE_URL, config, session, max_retries=retries)

    overview = parse_overview(overview_html)
    performance = parse_performance(performance_html)

    rows: list[IndustryRow] = []
    for key, meta in overview.items():
        perf = performance.get(key)
        if not perf:
            continue
        rows.append(
            IndustryRow(
                key=key,
                name=meta["name"],
                stocks=meta["stocks"],
                perf_w=perf["week"],
                perf_m=perf["month"],
                perf_q=perf["quarter"],
                perf_h=perf["half"],
                perf_y=perf["year"],
                finviz_url=meta["finviz_url"],
            )
        )
    if len(rows) < 100:
        raise RuntimeError(f"Finviz 行业数据过少（{len(rows)} 行）")
    return rows


def _industry_rows_from_storage(rows: list[dict[str, Any]]) -> list[IndustryRow]:
    return [
        IndustryRow(
            key=str(row["industry_key"]),
            name=str(row["name"]),
            stocks=int(row.get("stocks") or 0),
            perf_w=float(row.get("perf_w") or 0.0),
            perf_m=float(row.get("perf_m") or 0.0),
            perf_q=float(row.get("perf_q") or 0.0),
            perf_h=float(row.get("perf_h") or 0.0),
            perf_y=float(row.get("perf_y") or 0.0),
            finviz_url=str(row.get("finviz_url") or ""),
        )
        for row in rows
    ]


def _load_stale_industries(storage: Any) -> tuple[list[IndustryRow], str] | None:
    snapshot_date = storage.get_latest_date()
    if not snapshot_date:
        return None
    rows = storage.get_snapshot(snapshot_date)
    if len(rows) < 100:
        return None
    return _industry_rows_from_storage(rows), snapshot_date


def fetch_industries(
    config: dict[str, Any],
    storage: Any | None = None,
) -> list[IndustryRow]:
    try:
        return _fetch_industries_live(config)
    except RuntimeError as exc:
        if storage is not None and _stale_fallback_enabled(config):
            stale = _load_stale_industries(storage)
            if stale:
                rows, snapshot_date = stale
                logger.warning(
                    "Finviz 行业抓取失败，沿用缓存 %s: %s",
                    snapshot_date,
                    exc,
                )
                return rows
        raise


def fetch_industries_health_check(config: dict[str, Any]) -> tuple[bool, str]:
    """Lightweight Finviz reachability check (curl-first)."""
    try:
        html = _fetch_html_with_retry(
            "https://finviz.com/groups.ashx?g=industry&v=210&o=name",
            config,
            max_retries=1,
        )
        return len(html) > 500, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
