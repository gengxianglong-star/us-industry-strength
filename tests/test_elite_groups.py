"""Elite industry Groups pages."""

from __future__ import annotations

from unittest.mock import patch

from src.finviz_scraper import IndustryRow
from src.services.elite_groups import _merge_group_pages, fetch_elite_industry_rows


def _overview_html(n: int = 100) -> str:
    rows = []
    for i in range(n):
        rows.append(
            f'<tr><td><a href="screener?f=ind_industry{i}">Industry{i}</a></td>'
            f"<td>{10 + i}</td></tr>"
        )
    return (
        '<table class="groups_table"><tr><th>Name</th><th>Stocks</th></tr>'
        + "".join(rows)
        + "</table>"
    )


def _performance_html(n: int = 100) -> str:
    rows = []
    for i in range(n):
        rows.append(
            f'<tr><td><a href="screener?f=ind_industry{i}">Industry{i}</a></td>'
            "<td>1%</td><td>2%</td><td>3%</td><td>4%</td><td>5%</td></tr>"
        )
    return (
        '<table class="groups_table"><tr><th>Name</th>'
        "<th>Perf Week</th><th>Perf Month</th><th>Perf Quart</th>"
        "<th>Perf Half</th><th>Perf Year</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def test_merge_group_pages_builds_industry_rows() -> None:
    rows = _merge_group_pages(_overview_html(3), _performance_html(3))
    assert len(rows) == 3
    assert rows[0] == IndustryRow(
        key="industry0",
        name="Industry0",
        stocks=10,
        perf_w=1.0,
        perf_m=2.0,
        perf_q=3.0,
        perf_h=4.0,
        perf_y=5.0,
        finviz_url="https://finviz.com/screener?f=ind_industry0&v=141",
    )


def test_fetch_elite_industry_rows_parses_pages() -> None:
    with patch(
        "src.services.elite_groups._fetch_elite_group_pages",
        return_value=(_overview_html(100), _performance_html(100)),
    ):
        result = fetch_elite_industry_rows(auth_key="test-key")

    assert result is not None
    assert len(result) == 100
    assert result[0].key == "industry0"
    assert result[0].perf_q == 3.0


def test_fetch_elite_industry_rows_returns_none_without_auth() -> None:
    with patch("src.services.elite_groups.elite_auth_key", return_value=None):
        assert fetch_elite_industry_rows() is None


def test_fetch_elite_industry_rows_returns_none_on_fetch_error() -> None:
    with patch(
        "src.services.elite_groups._fetch_elite_group_pages",
        side_effect=RuntimeError("network down"),
    ):
        assert fetch_elite_industry_rows(auth_key="test-key") is None
