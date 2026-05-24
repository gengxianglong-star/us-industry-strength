"""Fetch and cache filtered stock picks for industries."""

from __future__ import annotations

from typing import Any

from src.finviz_stock_screener import fetch_industry_tickers
from src.scoring import ScoredIndustry, filter_top_strong
from src.storage import Storage


def fetch_and_store_stock_picks(
    storage: Storage,
    snapshot_date: str,
    industry_keys: list[str],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for key in industry_keys:
        try:
            payload = fetch_industry_tickers(key, config)
            storage.save_industry_stock_picks(
                snapshot_date,
                key,
                payload["tickers"],
                payload["screener_url"],
                payload["filters"],
            )
            results[key] = payload
        except Exception as exc:  # noqa: BLE001 - persist error for UI
            storage.save_industry_stock_picks(
                snapshot_date,
                key,
                [],
                "",
                "",
                error=str(exc),
            )
            results[key] = {"industry_key": key, "tickers": [], "error": str(exc)}
    return results


def fetch_top_industry_stock_picks(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    top = filter_top_strong(scored, config)
    keys = [item.key for item in top]
    if not keys:
        return {}
    return fetch_and_store_stock_picks(storage, snapshot_date, keys, config)
