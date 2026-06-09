"""Daily adjusted OHLC + volume for watchlist Lightweight Charts (yfinance)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from src.logging_config import get_logger

logger = get_logger(__name__)

CHART_BAR_LIMIT = 50
CHART_DISPLAY_BARS = 44

_ROOT = Path(__file__).resolve().parent.parent
_EXPORT_JSON_CANDIDATES = (
    _ROOT / "web" / "dist" / "data" / "rs_watchlist.json",
    _ROOT / "frontend" / "public" / "data" / "rs_watchlist.json",
)


def _ticker_dataframe(data: pd.DataFrame, symbol: str, symbols: list[str]) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    sym = symbol.upper()
    if len(symbols) == 1:
        df = data.copy()
    elif isinstance(data.columns, pd.MultiIndex):
        if sym not in data.columns.get_level_values(0):
            return pd.DataFrame()
        df = data[sym].copy()
    else:
        return pd.DataFrame()
    if "Close" not in df.columns:
        return pd.DataFrame()
    return df.dropna(subset=["Close"])


def _bars_from_dataframe(df: pd.DataFrame) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for date_idx, row in df.iterrows():
        bars.append(
            {
                "d": pd.Timestamp(date_idx).strftime("%Y-%m-%d"),
                "o": round(float(row["Open"]), 4),
                "h": round(float(row["High"]), 4),
                "l": round(float(row["Low"]), 4),
                "c": round(float(row["Close"]), 4),
                "v": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            }
        )
    return bars[-CHART_BAR_LIMIT:]


def fetch_symbols_bars_yf(symbols: list[str], *, timeout: int = 25) -> dict[str, list[dict[str, Any]]]:
    """Batch-fetch display OHLC for watchlist chart cards."""
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    unique = [s.upper() for s in symbols if s]
    if not unique:
        return bars_by_symbol

    logger.info("fetching chart bars for %d symbols via yfinance (3mo)", len(unique))
    try:
        data = yf.download(
            unique,
            period="3mo",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("yfinance chart batch failed: %s", exc)
        return {sym: [] for sym in unique}

    for sym in unique:
        try:
            df = _ticker_dataframe(data, sym, unique)
            bars_by_symbol[sym] = _bars_from_dataframe(df) if not df.empty else []
        except Exception as exc:  # noqa: BLE001
            logger.warning("chart bars parse failed for %s: %s", sym, exc)
            bars_by_symbol[sym] = []
    return bars_by_symbol


def load_cached_chart_bars_by_symbol() -> dict[str, list[dict[str, Any]]]:
    for path in _EXPORT_JSON_CANDIDATES:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("read cached watchlist charts failed %s: %s", path, exc)
            continue
        rows = payload.get("watchlist") or []
        cached: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            sym = str(row.get("symbol") or "").upper()
            bars = row.get("chart_bars") or []
            if sym and bars:
                cached[sym] = bars
        if cached:
            logger.info("loaded cached chart bars for %s symbols from %s", len(cached), path)
            return cached
    return {}


def attach_watchlist_chart_bars(
    watchlist: list[dict[str, Any]],
    *,
    timeout: int = 25,
) -> list[dict[str, Any]]:
    if not watchlist:
        return watchlist

    cached = load_cached_chart_bars_by_symbol()
    bars_by_symbol: dict[str, list[dict[str, Any]]] = dict(cached)

    need_fetch: list[str] = []
    for row in watchlist:
        sym = str(row.get("symbol") or "").upper()
        if not sym:
            continue
        existing = bars_by_symbol.get(sym) or row.get("chart_bars") or []
        if len(existing) < 10:
            need_fetch.append(sym)

    if need_fetch:
        bars_by_symbol.update(fetch_symbols_bars_yf(need_fetch, timeout=timeout))

    out: list[dict[str, Any]] = []
    for row in watchlist:
        sym = str(row.get("symbol") or "").upper()
        bars = bars_by_symbol.get(sym) or row.get("chart_bars") or []
        out.append({**row, "chart_bars": bars})
    return out


def enrich_watchlist_chart_bars(
    watchlist: list[dict[str, Any]],
    *,
    timeout: int = 25,
    skip_if_present: bool = False,
) -> list[dict[str, Any]]:
    if not watchlist:
        return watchlist

    symbols: list[str] = []
    for row in watchlist:
        sym = str(row.get("symbol") or "").upper()
        if not sym:
            continue
        if skip_if_present and len(row.get("chart_bars") or []) >= 10:
            continue
        symbols.append(sym)

    if not symbols:
        return watchlist

    bars_by_symbol = fetch_symbols_bars_yf(symbols, timeout=timeout)

    out: list[dict[str, Any]] = []
    for row in watchlist:
        sym = str(row.get("symbol") or "").upper()
        if skip_if_present and len(row.get("chart_bars") or []) >= 10:
            out.append(row)
            continue
        bars = bars_by_symbol.get(sym, [])
        out.append({**row, "chart_bars": bars})
    return out
