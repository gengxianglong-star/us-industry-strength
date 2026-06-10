"""Elite industry Groups export."""

from __future__ import annotations

from unittest.mock import patch

from src.services.elite_groups import fetch_elite_industry_rows


def _groups_csv(n: int = 100, *, link_suffix: str = "") -> str:
    header = "Name,Stocks,Perf Week,Perf Month,Perf Quart,Perf Half,Perf Year"
    if link_suffix:
        header += ",Link"
    lines = [header]
    for i in range(n):
        row = f"Industry{i},10,1%,2%,3%,4%,5%"
        if link_suffix:
            row += f",screener.ashx?f=ind_industry{i}"
        lines.append(row)
    return "\n".join(lines) + "\n"


def test_fetch_elite_industry_rows_parses_csv() -> None:
    with patch(
        "src.services.elite_groups._fetch_groups_export",
        return_value=_groups_csv(100),
    ):
        result = fetch_elite_industry_rows(auth_key="test-key")

    assert result is not None
    assert len(result) == 100
    assert result[0].key == "industry0"
    assert result[0].perf_q == 3.0
    assert "ind_industry0" in result[0].finviz_url


def test_fetch_elite_industry_rows_returns_none_without_auth() -> None:
    with patch("src.services.elite_groups.elite_auth_key", return_value=None):
        assert fetch_elite_industry_rows() is None


def test_fetch_elite_industry_rows_extracts_key_from_link() -> None:
    with patch(
        "src.services.elite_groups._fetch_groups_export",
        return_value=_groups_csv(100, link_suffix="1"),
    ):
        result = fetch_elite_industry_rows(auth_key="test-key")

    assert result is not None
    assert result[0].key == "industry0"
