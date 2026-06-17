"""Finviz Elite industry Groups — authenticated groups.ashx HTML (not export.ashx)."""

from __future__ import annotations

import time

from src.finviz_scraper import IndustryRow, parse_overview, parse_performance
from src.logging_config import get_logger
from src.services.elite_data import (
    ELITE_HOST,
    _elite_export_error_detail,
    _fetch_with_curl,
    _fetch_with_requests,
    _url_has_auth_param,
    elite_auth_key,
    elite_export_is_rate_limited,
    elite_rate_limit_wait,
)

logger = get_logger(__name__)

# export.ashx?v=140&g=industry returns full-market stocks, not industry groups.
ELITE_GROUPS_OVERVIEW = f"{ELITE_HOST}/groups.ashx?g=industry&o=name&v=110"
ELITE_GROUPS_PERFORMANCE = f"{ELITE_HOST}/groups.ashx?g=industry&o=-perf1m&v=142"
_MIN_INDUSTRY_ROWS = 100


def _validate_groups_html(text: str, *, final_url: str, label: str) -> None:
    if elite_export_is_rate_limited(body=text):
        raise RuntimeError(_elite_export_error_detail(429, text))
    if "invalid export api token" in (text or "").lower():
        raise RuntimeError(_elite_export_error_detail(401, text))
    lowered_url = final_url.lower()
    if lowered_url.rstrip("/").endswith("/elite"):
        raise RuntimeError(
            f"Elite groups {label}: redirected to login page — check FINVIZ_AUTH_KEY"
        )
    if "Name" not in text or "groups_table" not in text:
        raise RuntimeError(f"Elite groups {label}: page missing industry table")


def _fetch_groups_page(
    base_url: str,
    auth_key: str,
    *,
    label: str,
    timeout: int = 60,
    max_retries: int = 2,
) -> str:
    url = f"{base_url}&auth={auth_key}"
    use_cookies = not _url_has_auth_param(url)
    last_error: Exception | None = None
    for attempt in range(max_retries):
        elite_rate_limit_wait()
        try:
            text, final_url = _fetch_with_curl(url, timeout=timeout, use_cookies=use_cookies)
            _validate_groups_html(text, final_url=final_url, label=label)
            logger.info("Elite groups %s via curl OK (%d bytes)", label, len(text))
            return text
        except (OSError, RuntimeError) as exc:
            last_error = exc
            if elite_export_is_rate_limited(message=str(exc)) and attempt < max_retries - 1:
                logger.info("Elite groups rate limited — waiting 65s before retry")
                time.sleep(65)
                continue
            logger.debug("Elite groups %s curl attempt %d failed: %s", label, attempt + 1, exc)
        try:
            elite_rate_limit_wait()
            text, final_url = _fetch_with_requests(url, timeout=timeout, use_cookies=use_cookies)
            _validate_groups_html(text, final_url=final_url, label=label)
            logger.info("Elite groups %s via requests OK (%d bytes)", label, len(text))
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if elite_export_is_rate_limited(message=str(exc)) and attempt < max_retries - 1:
                logger.info("Elite groups rate limited — waiting 65s before retry")
                time.sleep(65)
                continue
            logger.debug("Elite groups %s requests attempt %d failed: %s", label, attempt + 1, exc)
        if attempt < max_retries - 1 and not elite_export_is_rate_limited(message=str(last_error or "")):
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Elite groups {label} fetch failed: {last_error}")


def _fetch_elite_group_pages(
    auth_key: str,
    *,
    timeout: int = 60,
    page_delay_seconds: float = 2.0,
) -> tuple[str, str]:
    overview_html = _fetch_groups_page(
        ELITE_GROUPS_OVERVIEW,
        auth_key,
        label="overview",
        timeout=timeout,
    )
    if page_delay_seconds > 0:
        time.sleep(page_delay_seconds)
    performance_html = _fetch_groups_page(
        ELITE_GROUPS_PERFORMANCE,
        auth_key,
        label="performance",
        timeout=timeout,
    )
    return overview_html, performance_html


def _merge_group_pages(overview_html: str, performance_html: str) -> list[IndustryRow]:
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


def fetch_elite_industry_rows(
    *,
    auth_key: str | None = None,
    timeout: int = 60,
) -> list[IndustryRow] | None:
    """Pull Finviz industry groups via authenticated Elite groups.ashx pages."""
    key = auth_key or elite_auth_key()
    if not key:
        logger.info("FINVIZ_AUTH_KEY not set; skipping Elite industry groups")
        return None

    logger.info("Elite industry engine: fetching groups pages (v=110 overview + v=142 performance)")
    try:
        overview_html, performance_html = _fetch_elite_group_pages(key, timeout=timeout)
        rows = _merge_group_pages(overview_html, performance_html)
    except RuntimeError as exc:
        logger.warning("%s; Elite industry groups unavailable", exc)
        return None

    if len(rows) < _MIN_INDUSTRY_ROWS:
        logger.warning(
            "Elite groups returned too few industries (%d); groups fetch unusable",
            len(rows),
        )
        return None

    logger.info("Elite industry data loaded: %d industries", len(rows))
    return rows
