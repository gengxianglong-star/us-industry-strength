"""RS + technical filters watchlist (no Finviz screener)."""

from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests

from src.logging_config import get_logger
logger = get_logger(__name__)

DEFAULT_WATCHLIST_CAP = 100
DEFAULT_MIN_AVG_30D_DOLLAR_VOLUME_USD = 100_000_000
AVG_DOLLAR_VOLUME_DAYS = 30
MIN_BARS_FOR_SMA200 = 200
_WATCHLIST_FETCH_WORKERS = 1
_WATCHLIST_FETCH_DELAY_SECONDS = 0.35


def watchlist_mode(config: dict[str, Any]) -> str:
    return str(config.get("stock_rs", {}).get("watchlist_mode", "rs_technical")).lower()


def use_rs_technical_watchlist(config: dict[str, Any]) -> bool:
    return watchlist_mode(config) != "finviz_cross"


def _resolve_params(config: dict[str, Any]) -> dict[str, Any]:
    rs_cfg = config.get("stock_rs", {})
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    return {
        "cross_top_percent": max(0.01, min(1.0, cross_top_percent)),
        "cap": max(1, int(rs_cfg.get("watchlist_cap", DEFAULT_WATCHLIST_CAP))),
        "min_avg_30d_dv": int(
            rs_cfg.get("min_avg_dollar_volume_30d_usd", DEFAULT_MIN_AVG_30D_DOLLAR_VOLUME_USD)
        ),
        "timeout": int(rs_cfg.get("request_timeout_seconds", 20)),
        "batch_size": max(5, int(rs_cfg.get("yahoo_batch_size", 40))),
        "batch_workers": max(1, int(rs_cfg.get("yahoo_batch_workers", 6))),
        "user_agent": (config.get("scraper") or {}).get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        ),
    }


def sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    return sum(window) / period


def passes_technical_momentum_filters(bars: list[dict[str, Any]]) -> bool:
    if len(bars) < MIN_BARS_FOR_SMA200:
        return False
    closes = [float(bar["close"]) for bar in bars]
    price = closes[-1]
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    if sma20 is None or sma50 is None or sma200 is None:
        return False
    return price > sma20 and sma20 > sma50 and price > sma200


def avg_dollar_volume(bars: list[dict[str, Any]], days: int = 30) -> float:
    if len(bars) < days:
        return 0.0
    tail = bars[-days:]
    total = 0.0
    for bar in tail:
        close = float(bar["close"])
        volume = float(bar.get("volume") or 0)
        total += close * volume
    return total / days


def filter_rs_technical_candidates(
    ranked_rows: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    *,
    cross_top_percent: float,
    cap: int,
    min_avg_30d_dv: int,
) -> list[dict[str, Any]]:
    if not ranked_rows:
        return []
    cutoff = max(1, int(len(ranked_rows) * cross_top_percent))
    passed: list[dict[str, Any]] = []
    for row in ranked_rows[:cutoff]:
        symbol = str(row["symbol"]).upper()
        bars = bars_by_symbol.get(symbol)
        if not bars or not passes_technical_momentum_filters(bars):
            continue
        if avg_dollar_volume(bars, AVG_DOLLAR_VOLUME_DAYS) < min_avg_30d_dv:
            continue
        passed.append(
            {
                "symbol": symbol,
                "rs_score": float(row["rs_score"]),
            }
        )

    passed.sort(key=lambda x: (-x["rs_score"], x["symbol"]))
    return passed[:cap]


def _finalize_watchlist_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda x: (-x["rs_score"], x["symbol"]))
    for idx, row in enumerate(ordered, start=1):
        row["rs_rank"] = idx
    return ordered


def _parse_yahoo_chart_daily_bars(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("chart", {}).get("result") or []
    if not result:
        return []
    first = result[0]
    timestamps = first.get("timestamp") or []
    quote = ((first.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((first.get("indicators") or {}).get("adjclose") or [{}])[0]
    closes = quote.get("close") or []
    adj_closes = adj.get("adjclose") or []
    volumes = quote.get("volume") or []
    if not timestamps or not closes:
        return []

    bars: list[dict[str, Any]] = []
    for idx, ts in enumerate(timestamps):
        if idx >= len(closes):
            break
        close = closes[idx]
        if idx < len(adj_closes) and adj_closes[idx] not in (None, 0):
            close = adj_closes[idx]
        if close in (None, 0):
            continue
        volume = volumes[idx] if idx < len(volumes) else None
        date_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        bars.append(
            {
                "date": date_iso,
                "close": float(close),
                "volume": float(volume) if volume not in (None, "") else None,
            }
        )
    bars.sort(key=lambda x: x["date"])
    return bars


def _fetch_symbol_daily_bars_curl(symbol: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    params = _resolve_params(config)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&range=2y"
    )
    cmd = (
        f"curl -sL --max-time {params['timeout']} --retry 2 --retry-delay 1 "
        f"-A \"{params['user_agent']}\" \"{url}\""
    )
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        bars = _parse_yahoo_chart_daily_bars(json.loads(result.stdout))
    except (ValueError, TypeError):
        return []
    if len(bars) >= MIN_BARS_FOR_SMA200:
        return bars
    return []


def _fetch_symbol_daily_bars(symbol: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    from src.stock_rs import fetch_yahoo_daily_bars

    bars = _fetch_symbol_daily_bars_curl(symbol, config)
    if bars:
        return bars

    params = _resolve_params(config)
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": params["user_agent"]})
    try:
        bars = fetch_yahoo_daily_bars(symbol, session, timeout=params["timeout"])
        if len(bars) >= MIN_BARS_FOR_SMA200:
            return bars
    except requests.RequestException as exc:
        logger.debug("yahoo daily bars failed for %s: %s", symbol, exc)
    return []


def fetch_daily_bars_map(
    symbols: list[str],
    config: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    if not symbols:
        return {}
    params = _resolve_params(config)
    unique = sorted({s.upper() for s in symbols if s})
    out: dict[str, list[dict[str, Any]]] = {}
    workers = min(_WATCHLIST_FETCH_WORKERS, len(unique)) or 1
    if workers == 1:
        for idx, symbol in enumerate(unique, start=1):
            bars = _fetch_symbol_daily_bars(symbol, config)
            if bars:
                out[symbol] = bars
            if idx % 50 == 0:
                logger.info("watchlist bar progress %d/%d", idx, len(unique))
            time.sleep(_WATCHLIST_FETCH_DELAY_SECONDS)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_fetch_symbol_daily_bars, symbol, config): symbol
                for symbol in unique
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    bars = future.result()
                    if bars:
                        out[symbol] = bars
                except Exception as exc:  # noqa: BLE001
                    logger.warning("watchlist bar fetch failed for %s: %s", symbol, exc)
                time.sleep(_WATCHLIST_FETCH_DELAY_SECONDS / workers)

    missing = [symbol for symbol in unique if symbol not in out]
    if missing:
        logger.info("watchlist bar retry for %d symbols", len(missing))
        for symbol in missing:
            bars = _fetch_symbol_daily_bars(symbol, config)
            if bars:
                out[symbol] = bars
            time.sleep(0.6)

    logger.info(
        "watchlist bars fetched %d/%d symbols (timeout=%ss)",
        len(out),
        len(unique),
        params["timeout"],
    )
    return out


def fetch_yahoo_industries(
    symbols: list[str],
    config: dict[str, Any],
) -> dict[str, str]:
    if not symbols:
        return {}
    params = _resolve_params(config)
    unique = sorted({s.upper() for s in symbols if s})
    out: dict[str, str] = {}
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": params["user_agent"]})
    chunk_size = 50
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    for start in range(0, len(unique), chunk_size):
        chunk = unique[start : start + chunk_size]
        try:
            resp = session.get(
                url,
                params={"symbols": ",".join(chunk)},
                timeout=params["timeout"],
            )
            if resp.status_code != 200:
                continue
            payload = resp.json()
            for item in (payload.get("quoteResponse") or {}).get("result") or []:
                symbol = str(item.get("symbol") or "").upper()
                industry = str(item.get("industry") or "").strip()
                if symbol and industry:
                    out[symbol] = industry
        except (requests.RequestException, ValueError) as exc:
            logger.warning("yahoo industry quote failed: %s", exc)
        time.sleep(0.15)
    return out


def build_rs_technical_watchlist(
    ranked_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Top RS% + SMA/liquidity filters; industry labels from Yahoo."""
    params = _resolve_params(config)
    cutoff = max(1, int(len(ranked_rows) * params["cross_top_percent"]))
    symbols = [str(row["symbol"]).upper() for row in ranked_rows[:cutoff]]
    bars_by_symbol = fetch_daily_bars_map(symbols, config)
    candidates = filter_rs_technical_candidates(
        ranked_rows,
        bars_by_symbol,
        cross_top_percent=params["cross_top_percent"],
        cap=params["cap"],
        min_avg_30d_dv=params["min_avg_30d_dv"],
    )
    industries = fetch_yahoo_industries([row["symbol"] for row in candidates], config)
    rows = [
        {
            "symbol": row["symbol"],
            "rs_score": row["rs_score"],
            "industries": [industries[row["symbol"]]] if industries.get(row["symbol"]) else [],
        }
        for row in candidates
    ]
    return _finalize_watchlist_ranks(rows)
