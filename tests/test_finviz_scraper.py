"""Tests for Finviz industry scraper fetch strategy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.finviz_scraper import (
    IndustryRow,
    _fetch_html_with_retry,
    fetch_industries,
)


SAMPLE_HTML = """
<html><body><table>
<tr><th>Name</th><th>Stocks</th><th>Perf Week</th><th>Perf Month</th>
<th>Perf Quart</th><th>Perf Half</th><th>Perf Year</th></tr>
<tr><td><a href="screener.ashx?f=ind_semiconductors">Semiconductors</a></td>
<td>50</td><td>1%</td><td>2%</td><td>3%</td><td>4%</td><td>5%</td></tr>
</table></body></html>
"""


def test_fetch_html_prefers_curl_when_configured() -> None:
    config = {"scraper": {"prefer_curl": True, "request_retries": 1}}
    with patch("src.finviz_scraper._fetch_text_with_curl", return_value=SAMPLE_HTML) as curl_mock:
        html = _fetch_html_with_retry("https://finviz.com/groups.ashx", config)
    assert "Semiconductors" in html
    curl_mock.assert_called_once()


def test_fetch_html_falls_back_to_curl_on_ssl_error() -> None:
    config = {"scraper": {"prefer_curl": False, "request_retries": 1}}
    ssl_error = requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")

    with (
        patch("src.finviz_scraper._prepare_session") as prep_mock,
        patch("src.finviz_scraper._fetch_text_with_requests", side_effect=ssl_error),
        patch("src.finviz_scraper._fetch_text_with_curl", return_value=SAMPLE_HTML) as curl_mock,
    ):
        prep_mock.return_value = MagicMock()
        html = _fetch_html_with_retry("https://finviz.com/groups.ashx", config)
    assert "Semiconductors" in html
    curl_mock.assert_called_once()


def test_fetch_industries_uses_stale_snapshot_on_failure() -> None:
    storage = MagicMock()
    storage.get_latest_date.return_value = "2026-05-29"
    storage.get_snapshot.return_value = [
        {
            "industry_key": "semiconductors",
            "name": "Semiconductors",
            "stocks": 50,
            "perf_w": 1.0,
            "perf_m": 2.0,
            "perf_q": 3.0,
            "perf_h": 4.0,
            "perf_y": 5.0,
            "finviz_url": "https://finviz.com/screener?f=ind_semiconductors",
        }
    ] * 120

    config = {"scraper": {"stale_fallback_enabled": True}}
    with patch(
        "src.finviz_scraper._fetch_industries_live",
        side_effect=RuntimeError("ssl failed"),
    ):
        rows = fetch_industries(config, storage=storage)

    assert len(rows) == 120
    assert isinstance(rows[0], IndustryRow)
    assert rows[0].key == "semiconductors"


def test_cloudflare_detection_ignores_insights_beacon() -> None:
    html = '<script src="https://static.cloudflareinsights.com/beacon.min.js"></script><table><th>Name</th>'
    from src.finviz_scraper import _is_cloudflare_page

    assert not _is_cloudflare_page(html)


def test_fetch_industries_raises_without_stale_cache() -> None:
    config = {"scraper": {"stale_fallback_enabled": True}}
    with (
        patch(
            "src.finviz_scraper._fetch_industries_live",
            side_effect=RuntimeError("ssl failed"),
        ),
        pytest.raises(RuntimeError, match="ssl failed"),
    ):
        fetch_industries(config, storage=None)
