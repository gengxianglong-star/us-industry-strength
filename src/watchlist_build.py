"""RS + technical filters watchlist (no Finviz screener)."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

from src.logging_config import get_logger
from src.yfinance_util import disable_yfinance_disk_cache, download_prices

disable_yfinance_disk_cache()

logger = get_logger(__name__)

DEFAULT_WATCHLIST_CAP = 100
DEFAULT_MIN_AVG_30D_DOLLAR_VOLUME_USD = 100_000_000
AVG_DOLLAR_VOLUME_DAYS = 30
MIN_BARS_FOR_SMA200 = 200


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
        "user_agent": (config.get("scraper") or {}).get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        ),
    }


def _ticker_dataframe(data: pd.DataFrame, symbol: str, tickers: list[str]) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    sym = symbol.upper()
    if len(tickers) == 1:
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


def passes_technical_momentum_filters(df: pd.DataFrame, min_avg_30d_dv: int) -> bool:
    if len(df) < MIN_BARS_FOR_SMA200:
        return False

    close_series = df["Close"]
    sma20 = close_series.rolling(20).mean().iloc[-1]
    sma50 = close_series.rolling(50).mean().iloc[-1]
    sma200 = close_series.rolling(200).mean().iloc[-1]
    price = close_series.iloc[-1]

    if pd.isna(sma20) or pd.isna(sma50) or pd.isna(sma200):
        return False
    if not (price > sma20 > sma50 and price > sma200):
        return False

    tail = df.tail(AVG_DOLLAR_VOLUME_DAYS)
    if "Volume" not in tail.columns or len(tail) < AVG_DOLLAR_VOLUME_DAYS:
        return False
    avg_dv = (tail["Close"] * tail["Volume"]).mean()
    return bool(avg_dv >= min_avg_30d_dv)


def _finalize_watchlist_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda x: (-x["rs_score"], x["symbol"]))
    for idx, row in enumerate(ordered, start=1):
        row["rs_rank"] = idx
    return ordered


def _download_watchlist_bars(tickers: list[str], *, timeout: int) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    return download_prices(
        tickers,
        period="2y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        timeout=timeout,
        threads=False,
    )


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
    """RS-ordered batch fetch with early stop at watchlist cap."""
    params = _resolve_params(config)
    cutoff = max(1, int(len(ranked_rows) * params["cross_top_percent"]))
    sorted_candidates = sorted(
        ranked_rows[:cutoff],
        key=lambda x: float(x.get("rs_score", 0)),
        reverse=True,
    )

    target_cap = params["cap"]
    min_avg_30d_dv = params["min_avg_30d_dv"]
    batch_size = params["batch_size"]
    passed: list[dict[str, Any]] = []

    logger.info(
        "watchlist build: %d RS candidates, cap=%d, batch_size=%d",
        len(sorted_candidates),
        target_cap,
        batch_size,
    )

    for start in range(0, len(sorted_candidates), batch_size):
        if len(passed) >= target_cap:
            logger.info("watchlist cap reached; early stop before batch at offset %d", start)
            break

        chunk_rows = sorted_candidates[start : start + batch_size]
        tickers = [str(row["symbol"]).upper() for row in chunk_rows]
        try:
            data = _download_watchlist_bars(tickers, timeout=params["timeout"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance batch download failed: %s", exc)
            continue

        for row in chunk_rows:
            if len(passed) >= target_cap:
                break
            symbol = str(row["symbol"]).upper()
            try:
                df = _ticker_dataframe(data, symbol, tickers)
                if df.empty:
                    continue
                if passes_technical_momentum_filters(df, min_avg_30d_dv):
                    passed.append(
                        {
                            "symbol": symbol,
                            "rs_score": float(row["rs_score"]),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("watchlist filter failed for %s: %s", symbol, exc)

        time.sleep(0.35)

    industries = fetch_yahoo_industries([row["symbol"] for row in passed], config)
    rows = [
        {
            "symbol": row["symbol"],
            "rs_score": row["rs_score"],
            "industries": [industries[row["symbol"]]] if industries.get(row["symbol"]) else [],
        }
        for row in passed
    ]
    logger.info("watchlist build done: %d symbols passed filters", len(rows))
    return _finalize_watchlist_ranks(rows)
