"""Fetch and parse Finviz Industry group data (no Elite required)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup

OVERVIEW_URL = "https://finviz.com/groups.ashx?g=industry&o=name&v=110"
PERFORMANCE_URL = "https://finviz.com/groups.ashx?g=industry&o=-perf1m&v=142"

INDUSTRY_KEY_RE = re.compile(r"f=ind_([^\"&]+)")


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


def _fetch_html(url: str, user_agent: str) -> str:
    response = requests.get(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.text


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
    user_agent = scraper.get("user_agent", "Mozilla/5.0")
    delay = float(scraper.get("request_delay_seconds", 1.0))

    overview_html = _fetch_html(OVERVIEW_URL, user_agent)
    time.sleep(delay)
    performance_html = _fetch_html(PERFORMANCE_URL, user_agent)

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
