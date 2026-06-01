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

OVERVIEW_URL = "https://finviz.com/groups.ashx?g=industry&o=name&v=110"
PERFORMANCE_URL = "https://finviz.com/groups.ashx?g=industry&o=-perf1m&v=142"
FINVIZ_HOME = "https://finviz.com/"

INDUSTRY_KEY_RE = re.compile(r"f=ind_([^\"&]+)")

CLOUDFLARE_MARKERS = [
    "Cloudflare",
    "cf-challenge",
    "cf-browser-verify",
    "cf_captcha",
    "cf-wrapper",
    "Checking your browser",
    "captcha-bypass",
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


def _fetch_text_with_requests(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=45)
    response.raise_for_status()
    return response.text


def _fetch_text_with_curl(url: str, user_agent: str, cookie_file: str) -> str:
    cmd = [
        "curl", "-sL", "--max-time", "45",
        "-A", user_agent,
        "-e", FINVIZ_HOME,
    ]
    if cookie_file and Path(cookie_file).is_file():
        cmd.extend(["-b", cookie_file])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"curl 抓取 Finviz 失败: {result.stderr.strip() or result.returncode}")
    return result.stdout


def _prepare_session(user_agent: str, cookie_file: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    })
    if cookie_file and Path(cookie_file).is_file():
        with Path(cookie_file).open(encoding="utf-8", errors="ignore") as handle:
            session.headers["Cookie"] = handle.read().strip()
    session.get(FINVIZ_HOME, timeout=30)
    time.sleep(0.5)
    return session


def _fetch_html_with_retry(
    url: str,
    config: dict[str, Any],
    session: requests.Session | None = None,
    max_retries: int = 3,
) -> str:
    """Fetch HTML with retry, Cloudflare detection, and curl fallback."""
    scraper = config.get("scraper", {})
    user_agent = scraper.get("user_agent", "Mozilla/5.0")
    delay = float(scraper.get("request_delay_seconds", 1.0))
    cookie_file = str(scraper.get("cookie_file") or "").strip()

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            # Requests attempt
            if session is None:
                session = _prepare_session(user_agent, cookie_file)
            html = _fetch_text_with_requests(session, url)
            if _is_cloudflare_page(html):
                if attempt < max_retries - 1:
                    time.sleep(delay * (attempt + 1))
                    session = None  # force re-prepare session
                    continue
                # Final attempt: fall back to curl
                html = _fetch_text_with_curl(url, user_agent, cookie_file)
                if _is_cloudflare_page(html):
                    raise RuntimeError(f"Finviz 返回 Cloudflare 验证页面 ({url})")
            return html
        except (requests.RequestException, OSError, RuntimeError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
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


def fetch_industries(config: dict[str, Any]) -> list[IndustryRow]:
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
    return rows
