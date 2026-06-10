"""Finviz Elite industry Groups export — replaces HTML scraper when auth is set."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from src.finviz_scraper import INDUSTRY_KEY_RE, IndustryRow
from src.logging_config import get_logger
from src.services.elite_data import (
    ELITE_HOST,
    _fetch_with_curl,
    _fetch_with_requests,
    _looks_like_html_error,
    _pick,
    _url_has_auth_param,
    elite_auth_key,
    parse_finviz_number,
    parse_finviz_percent,
)

logger = get_logger(__name__)

ELITE_GROUPS_EXPORT = f"{ELITE_HOST}/export.ashx?v=140&g=industry"

_NAME_ALIASES = ("Name", "Industry", "Group")
_STOCKS_ALIASES = ("Stocks", "No. of Stocks", "# Stocks", "Number of Stocks")
_PERF_ALIASES: dict[str, tuple[str, ...]] = {
    "perf_w": ("Performance (Week)", "Perf Week"),
    "perf_m": ("Performance (Month)", "Perf Month"),
    "perf_q": ("Performance (Quarter)", "Perf Quart", "Performance (Quarter)"),
    "perf_h": ("Performance (Half Year)", "Perf Half", "Performance (Half)"),
    "perf_y": ("Performance (Year)", "Perf Year", "Performance (YTD)"),
}


def _slug_industry_key(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "", name.lower())
    return slug or name.lower().replace(" ", "_")


def _extract_industry_key(row: dict[str, str], name: str) -> str:
    for val in row.values():
        if not isinstance(val, str):
            continue
        match = INDUSTRY_KEY_RE.search(val)
        if match:
            return match.group(1)
    return _slug_industry_key(name)


def _parse_groups_csv(text: str) -> list[dict[str, str]]:
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _validate_groups_body(text: str, *, final_url: str) -> None:
    lowered_url = final_url.lower()
    if lowered_url.rstrip("/").endswith("/elite"):
        raise RuntimeError(
            "Elite groups: redirected to login page — check FINVIZ_AUTH_KEY"
        )
    if _looks_like_html_error(text):
        raise RuntimeError("Elite groups: response is HTML, not CSV")
    rows = _parse_groups_csv(text)
    if not rows:
        raise RuntimeError("Elite groups: CSV parsed to zero rows")
    first = rows[0]
    if not _pick(first, _NAME_ALIASES):
        raise RuntimeError(
            f"Elite groups: CSV missing Name column (headers={list(first.keys())[:8]})"
        )


def _fetch_groups_export(auth_key: str, *, timeout: int = 60, max_retries: int = 3) -> str:
    url = f"{ELITE_GROUPS_EXPORT}&auth={auth_key}"
    use_cookies = not _url_has_auth_param(url)
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            text, final_url = _fetch_with_curl(url, timeout=timeout, use_cookies=use_cookies)
            _validate_groups_body(text, final_url=final_url)
            logger.info("Elite groups export via curl OK (%d bytes)", len(text))
            return text
        except (OSError, RuntimeError) as exc:
            last_error = exc
            logger.debug("Elite groups curl attempt %d failed: %s", attempt + 1, exc)
        try:
            text, final_url = _fetch_with_requests(url, timeout=timeout, use_cookies=use_cookies)
            _validate_groups_body(text, final_url=final_url)
            logger.info("Elite groups export via requests OK (%d bytes)", len(text))
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.debug("Elite groups requests attempt %d failed: %s", attempt + 1, exc)
        if attempt < max_retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Elite groups export failed: {last_error}")


def _row_to_industry(row: dict[str, str]) -> IndustryRow | None:
    name = _pick(row, _NAME_ALIASES)
    if not name:
        return None
    key = _extract_industry_key(row, name)
    stocks_raw = _pick(row, _STOCKS_ALIASES)
    stocks = int(parse_finviz_number(stocks_raw) or 0)

    perf: dict[str, float] = {}
    for attr, aliases in _PERF_ALIASES.items():
        parsed = parse_finviz_percent(_pick(row, aliases))
        if parsed is None:
            return None
        perf[attr] = parsed

    return IndustryRow(
        key=key,
        name=name,
        stocks=stocks,
        perf_w=perf["perf_w"],
        perf_m=perf["perf_m"],
        perf_q=perf["perf_q"],
        perf_h=perf["perf_h"],
        perf_y=perf["perf_y"],
        finviz_url=f"https://finviz.com/screener?f=ind_{key}&v=141",
    )


def fetch_elite_industry_rows(
    *,
    auth_key: str | None = None,
    timeout: int = 60,
) -> list[IndustryRow] | None:
    """Pull all Finviz industry groups via Elite CSV export."""
    key = auth_key or elite_auth_key()
    if not key:
        logger.info("FINVIZ_AUTH_KEY not set; skipping Elite industry groups")
        return None

    logger.info("Elite industry engine: fetching groups export (v=140, g=industry)")
    try:
        text = _fetch_groups_export(key, timeout=timeout)
    except RuntimeError as exc:
        logger.warning("%s; falling back to HTML scraper", exc)
        return None

    rows: list[IndustryRow] = []
    for raw in _parse_groups_csv(text):
        item = _row_to_industry(raw)
        if item is not None:
            rows.append(item)

    if len(rows) < 100:
        logger.warning(
            "Elite groups returned too few industries (%d); falling back to scraper",
            len(rows),
        )
        return None

    logger.info("Elite industry data loaded: %d industries", len(rows))
    return rows
