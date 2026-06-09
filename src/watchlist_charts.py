"""Daily adjusted OHLC + volume for watchlist Lightweight Charts (Yahoo)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.logging_config import get_logger

logger = get_logger(__name__)

# ~2.5 months exported (enough warmup for SMA50 on the last visible bar)
CHART_BAR_LIMIT = 50
# Frontend displays the last 44 sessions (~2 months)
CHART_DISPLAY_BARS = 44
_MAX_WORKERS = 3
_RETRY_DELAYS = (0.6, 1.2, 2.0)

_ROOT = Path(__file__).resolve().parent.parent
_EXPORT_JSON_CANDIDATES = (
    _ROOT / "web" / "dist" / "data" / "rs_watchlist.json",
    _ROOT / "frontend" / "public" / "data" / "rs_watchlist.json",
)


def _adjust_factor(close: float | None, adj_close: float | None) -> float:
    if close in (None, 0) or adj_close in (None, 0):
        return 1.0
    return float(adj_close) / float(close)


def _parse_yahoo_chart_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("chart", {}).get("result") or []
    if not result:
        return []
    first = result[0]
    timestamps = first.get("timestamp") or []
    quote = ((first.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((first.get("indicators") or {}).get("adjclose") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    adj_closes = adj.get("adjclose") or []
    if not timestamps or not closes:
        return []

    bars: list[dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        if idx >= len(closes):
            break
        close = closes[idx]
        if close in (None, 0):
            continue
        open_ = opens[idx] if idx < len(opens) else close
        high = highs[idx] if idx < len(highs) else close
        low = lows[idx] if idx < len(lows) else close
        if open_ in (None, 0) or high in (None, 0) or low in (None, 0):
            continue
        adj_close = adj_closes[idx] if idx < len(adj_closes) else None
        factor = _adjust_factor(close, adj_close)
        volume = volumes[idx] if idx < len(volumes) else None
        date_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        adj_c = float(adj_close) if adj_close not in (None, 0) else float(close)
        bars.append(
            {
                "d": date_iso,
                "o": round(float(open_) * factor, 4),
                "h": round(float(high) * factor, 4),
                "l": round(float(low) * factor, 4),
                "c": round(adj_c, 4),
                "v": int(volume) if volume not in (None, "") else 0,
            }
        )
    bars.sort(key=lambda x: x["d"])
    return bars[-CHART_BAR_LIMIT:]


def fetch_yahoo_ohlc_bars(
    symbol: str,
    session: requests.Session,
    timeout: int = 25,
) -> list[dict[str, Any]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1y"
    for attempt, delay in enumerate(_RETRY_DELAYS):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 429:
                time.sleep(delay)
                continue
            if resp.status_code != 200:
                if attempt + 1 < len(_RETRY_DELAYS):
                    time.sleep(delay)
                    continue
                return []
            bars = _parse_yahoo_chart_payload(resp.json())
            if bars:
                return bars
        except (requests.RequestException, ValueError):
            if attempt + 1 < len(_RETRY_DELAYS):
                time.sleep(delay)
                continue
            return []
        time.sleep(delay)
    return []


def _fetch_one(symbol: str, timeout: int) -> tuple[str, list[dict[str, Any]]]:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    return symbol, fetch_yahoo_ohlc_bars(symbol, session, timeout=timeout)


def _fetch_symbols_bars(symbols: list[str], *, timeout: int = 25) -> dict[str, list[dict[str, Any]]]:
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    if not symbols:
        return bars_by_symbol

    workers = min(_MAX_WORKERS, max(1, len(symbols)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, sym, timeout): sym for sym in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                _, bars = fut.result()
                bars_by_symbol[sym] = bars
            except Exception as exc:  # noqa: BLE001
                logger.warning("chart bars failed for %s: %s", sym, exc)
                bars_by_symbol[sym] = []

    missing = [sym for sym in symbols if not bars_by_symbol.get(sym)]
    for sym in missing:
        time.sleep(0.8)
        try:
            _, bars = _fetch_one(sym, timeout)
            if bars:
                bars_by_symbol[sym] = bars
                logger.info("chart bars recovered for %s on retry pass", sym)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chart bars retry failed for %s: %s", sym, exc)
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
        fetched = _fetch_symbols_bars(need_fetch, timeout=timeout)
        bars_by_symbol.update(fetched)

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
    skip_if_present: bool = True,
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

    bars_by_symbol = _fetch_symbols_bars(symbols, timeout=timeout)

    out: list[dict[str, Any]] = []
    for row in watchlist:
        sym = str(row.get("symbol") or "").upper()
        if skip_if_present and len(row.get("chart_bars") or []) >= 10:
            out.append(row)
            continue
        bars = bars_by_symbol.get(sym, [])
        out.append({**row, "chart_bars": bars})
    return out
