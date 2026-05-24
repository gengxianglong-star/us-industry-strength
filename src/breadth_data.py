"""Fetch and parse Stockbee market breadth data."""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime
from typing import Any

import requests

BREADTH_CSV_URL = (
    "https://docs.google.com/spreadsheets/u/0/d/"
    "1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE/pub?output=csv"
)

_CACHE_TTL_SECONDS = 300
_CACHE_DATA: dict[str, Any] | None = None
_CACHE_AT: float = 0.0


def _to_number(value: str) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        dt = datetime.strptime(text, "%m/%d/%Y")
        return dt.date().isoformat()
    except ValueError:
        return text


def _fetch_raw_rows() -> list[list[str]]:
    resp = requests.get(BREADTH_CSV_URL, timeout=25)
    resp.raise_for_status()
    return list(csv.reader(io.StringIO(resp.text)))


def load_breadth_data(force_refresh: bool = False) -> dict[str, Any]:
    global _CACHE_DATA, _CACHE_AT
    now = time.time()
    if not force_refresh and _CACHE_DATA and (now - _CACHE_AT) < _CACHE_TTL_SECONDS:
        return _CACHE_DATA

    rows = _fetch_raw_rows()
    if len(rows) < 3:
        raise ValueError("市场宽度数据格式异常：行数不足")

    group_row = rows[0]
    header_row = rows[1]
    data_rows = rows[2:]
    headers = [h.strip() for h in header_row]

    normalized_rows: list[dict[str, Any]] = []
    for row in data_rows:
        if not row or not row[0].strip():
            continue
        item: dict[str, Any] = {"date": _parse_date(row[0]), "raw_date": row[0].strip()}
        for idx, header in enumerate(headers[1:], start=1):
            key = f"c{idx}"
            val = row[idx].strip() if idx < len(row) else ""
            item[key] = val
            item[f"{key}_num"] = _to_number(val)
        normalized_rows.append(item)

    parsed = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "group_headers": [h.strip() for h in group_row],
        "headers": headers,
        "rows": normalized_rows,
        "source": BREADTH_CSV_URL,
        "notes": {
            "indicators_explain_url": "https://stockbee.blogspot.com/2022/12/market-monitor-scans.html",
            "overview_url": "https://stockbee.blogspot.com/p/mm.html",
            "sheet_public_url": (
                "https://docs.google.com/spreadsheets/u/0/d/"
                "1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE/pub?output=html&widget=true"
            ),
            "formula_note": "公开接口可读取指标数值，无法直接返回 Google Sheet 条件格式公式文本。",
        },
    }
    _CACHE_DATA = parsed
    _CACHE_AT = now
    return parsed
