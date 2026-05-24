"""Compute US stock relative strength (RS) from free sources."""

from __future__ import annotations

import csv
import ftplib
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from src.config_loader import TIMEFRAMES
from src.scoring import ScoredIndustry, filter_top_strong
from src.storage import Storage

PERF_INDEX_OFFSETS = {
    "week": 5,
    "month": 21,
    "quarter": 63,
    "half": 126,
    "year": 252,
}

PERF_KEY_MAP = {
    "week": "perf_w",
    "month": "perf_m",
    "quarter": "perf_q",
    "half": "perf_h",
    "year": "perf_y",
}


def _percentile(rank: int, total: int) -> float:
    if total <= 1:
        return 1.0
    return 1.0 - (rank - 1) / (total - 1)


def _download_nasdaq_file(filename: str, timeout: int = 25) -> str:
    chunks: list[str] = []
    ftp = ftplib.FTP("ftp.nasdaqtrader.com", timeout=timeout)
    try:
        ftp.login()
        ftp.cwd("/SymbolDirectory")
        ftp.retrlines(f"RETR {filename}", chunks.append)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
    return "\n".join(chunks)


def _is_common_symbol(symbol: str) -> bool:
    if not symbol:
        return False
    bad_tokens = ("$", "^", "/", " ")
    return all(token not in symbol for token in bad_tokens)


def load_us_universe_from_nasdaq() -> list[dict[str, Any]]:
    nasdaq_text = _download_nasdaq_file("nasdaqlisted.txt")
    other_text = _download_nasdaq_file("otherlisted.txt")

    symbols: dict[str, dict[str, Any]] = {}

    nasdaq_rows = csv.DictReader(io.StringIO(nasdaq_text), delimiter="|")
    for row in nasdaq_rows:
        symbol = (row.get("Symbol") or "").strip().upper()
        if symbol in {"", "File Creation Time"}:
            continue
        if row.get("Test Issue", "N") == "Y":
            continue
        if row.get("ETF", "N") == "Y":
            continue
        if not _is_common_symbol(symbol):
            continue
        symbols[symbol] = {
            "symbol": symbol,
            "name": (row.get("Security Name") or "").strip(),
            "exchange": "NASDAQ",
        }

    other_rows = csv.DictReader(io.StringIO(other_text), delimiter="|")
    for row in other_rows:
        symbol = (row.get("ACT Symbol") or "").strip().upper()
        if symbol in {"", "File Creation Time"}:
            continue
        if row.get("Test Issue", "N") == "Y":
            continue
        if row.get("ETF", "N") == "Y":
            continue
        if not _is_common_symbol(symbol):
            continue
        exchange = (row.get("Exchange") or "").strip().upper()
        symbols.setdefault(
            symbol,
            {
                "symbol": symbol,
                "name": (row.get("Security Name") or "").strip(),
                "exchange": exchange or "OTHER",
            },
        )

    return sorted(symbols.values(), key=lambda x: x["symbol"])


def _stooq_symbol_candidates(symbol: str) -> list[str]:
    s = symbol.lower()
    candidates = [s]
    if "." in s:
        candidates.append(s.replace(".", "-"))
    if "-" in s:
        candidates.append(s.replace("-", "."))
    seen: set[str] = set()
    uniq: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def _parse_stooq_csv(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if text.lower().startswith("get your apikey"):
        return []
    rows = list(csv.DictReader(io.StringIO(text)))
    bars: list[dict[str, Any]] = []
    for row in rows:
        date_val = (row.get("Date") or "").strip()
        close_val = row.get("Close")
        if not date_val or not close_val or close_val in {"0", "0.0"}:
            continue
        try:
            close_num = float(close_val)
        except ValueError:
            continue
        volume_num: float | None = None
        volume_val = row.get("Volume")
        if volume_val not in {None, "", "0"}:
            try:
                volume_num = float(volume_val)
            except ValueError:
                volume_num = None
        bars.append({"date": date_val, "close": close_num, "volume": volume_num})
    bars.sort(key=lambda x: x["date"])
    return bars


def fetch_stooq_daily_bars(
    symbol: str,
    session: requests.Session,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    for candidate in _stooq_symbol_candidates(symbol):
        url = f"http://stooq.com/q/d/l/?s={candidate}.us&i=d"
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code != 200:
                continue
            bars = _parse_stooq_csv(resp.text)
            if bars:
                return bars
        except requests.RequestException:
            continue
    return []


def fetch_yahoo_daily_bars(
    symbol: str,
    session: requests.Session,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2y"
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code != 200:
            return []
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return []

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


def fetch_yahoo_batch_daily_bars(
    symbols: list[str],
    session: requests.Session,
    timeout: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    if not symbols:
        return {}
    url = "https://query1.finance.yahoo.com/v7/finance/spark"
    try:
        resp = session.get(
            url,
            params={
                "symbols": ",".join(symbols),
                "range": "2y",
                "interval": "1d",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return {}
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return {}

    results = (payload.get("spark") or {}).get("result") or []
    out: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        symbol = str(item.get("symbol") or "").upper()
        response = (item.get("response") or [{}])[0]
        timestamps = response.get("timestamp") or []
        quote = ((response.get("indicators") or {}).get("quote") or [{}])[0]
        adj = ((response.get("indicators") or {}).get("adjclose") or [{}])[0]
        closes = quote.get("close") or []
        adj_closes = adj.get("adjclose") or []
        volumes = quote.get("volume") or []
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
        out[symbol] = bars
    return out


def _calc_performance(bars: list[dict[str, Any]]) -> dict[str, float] | None:
    if len(bars) < PERF_INDEX_OFFSETS["year"] + 1:
        return None
    closes = [float(bar["close"]) for bar in bars]
    last = closes[-1]
    if last <= 0:
        return None
    result: dict[str, float] = {}
    for tf, offset in PERF_INDEX_OFFSETS.items():
        prev = closes[-1 - offset]
        if prev <= 0:
            return None
        result[PERF_KEY_MAP[tf]] = (last / prev - 1.0) * 100.0
    return result


def _rank_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    ordered = sorted(rows, key=lambda x: x[key], reverse=True)
    return {row["symbol"]: idx + 1 for idx, row in enumerate(ordered)}


def compute_and_store_stock_rs(
    storage: Storage,
    snapshot_date: str,
    scored_industries: list[ScoredIndustry],
    config: dict[str, Any],
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    rs_cfg = config.get("stock_rs", {})
    request_timeout = int(rs_cfg.get("request_timeout_seconds", 20))
    min_price_rows = int(rs_cfg.get("min_price_rows", 260))
    max_workers = int(rs_cfg.get("max_workers", 24))
    max_workers = max(4, min(64, max_workers))
    save_price_history = bool(rs_cfg.get("save_price_history", False))
    incremental_mode = bool(rs_cfg.get("incremental_mode", True))
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    cross_top_percent = max(0.01, min(1.0, cross_top_percent))
    tier_a = float(rs_cfg.get("tier_a_score", 0.8))
    tier_b = float(rs_cfg.get("tier_b_score", 0.65))
    universe_cap = int(rs_cfg.get("universe_cap", 0))
    prefer_stooq = bool(rs_cfg.get("prefer_stooq", False))

    universe = load_us_universe_from_nasdaq()
    if universe_cap > 0:
        universe = universe[:universe_cap]
    storage.upsert_stock_universe(universe, source="nasdaqtrader")
    symbols = [row["symbol"] for row in universe]
    symbol_set = set(symbols)

    existing_rows = storage.get_stock_rs_raw(snapshot_date) if incremental_mode else []
    existing_perf_map: dict[str, dict[str, Any]] = {
        row["symbol"]: {
            "symbol": row["symbol"],
            "perf_w": float(row["perf_w"]),
            "perf_m": float(row["perf_m"]),
            "perf_q": float(row["perf_q"]),
            "perf_h": float(row["perf_h"]),
            "perf_y": float(row["perf_y"]),
        }
        for row in existing_rows
        if row["symbol"] in symbol_set
    }
    existing_issues = (
        {k: v for k, v in storage.get_stock_rs_issues(snapshot_date).items() if k in symbol_set}
        if incremental_mode
        else {}
    )

    if incremental_mode and (existing_perf_map or existing_issues):
        issue_symbols = {s for s in existing_issues.keys() if s in symbol_set}
        missing_symbols = {s for s in symbols if s not in existing_perf_map}
        target_symbols = sorted(issue_symbols | missing_symbols)
    else:
        target_symbols = symbols

    perf_map = dict(existing_perf_map)
    issues_map = dict(existing_issues)

    worker_errors: list[str] = []

    user_agent = "Mozilla/5.0"
    total_symbols = len(target_symbols)
    processed = 0
    if progress_callback:
        progress_callback(0, total_symbols)

    def _fetch_one(symbol: str) -> dict[str, Any]:
        with requests.Session() as session:
            session.headers.update({"User-Agent": user_agent})
            bars: list[dict[str, Any]] = []
            source = "yahoo"
            if prefer_stooq:
                bars = fetch_stooq_daily_bars(symbol, session, timeout=request_timeout)
                source = "stooq"
            if not bars:
                bars = fetch_yahoo_daily_bars(symbol, session, timeout=request_timeout)
                source = "yahoo"
        if not bars:
            return {"symbol": symbol, "status": "no_bars", "reason": "no_bars"}
        if len(bars) < min_price_rows:
            return {
                "symbol": symbol,
                "status": "insufficient_history",
                "reason": "insufficient_history",
            }
        perf = _calc_performance(bars)
        if not perf:
            return {"symbol": symbol, "status": "perf_invalid", "reason": "perf_invalid"}
        return {
            "symbol": symbol,
            "status": "ok",
            "source": source,
            "bars": bars[-320:],
            "perf": perf,
        }

    if target_symbols:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_one, symbol) for symbol in target_symbols]
            for future in as_completed(futures):
                try:
                    payload = future.result()
                except Exception as exc:  # noqa: BLE001
                    if len(worker_errors) < 20:
                        worker_errors.append(str(exc))
                    payload = {"status": "no_bars", "reason": "no_bars", "symbol": ""}

                status = payload.get("status")
                symbol = str(payload.get("symbol") or "")
                if status == "ok" and symbol:
                    if save_price_history:
                        storage.replace_stock_price_history(
                            symbol,
                            payload["bars"],
                            source=payload.get("source", "yahoo"),
                        )
                    perf_map[symbol] = {"symbol": symbol, **payload["perf"]}
                    issues_map.pop(symbol, None)
                elif symbol:
                    issues_map[symbol] = str(payload.get("reason") or "no_bars")

                processed += 1
                if progress_callback and (processed % 25 == 0 or processed == total_symbols):
                    progress_callback(processed, total_symbols)
    elif progress_callback:
        progress_callback(0, 0)

    rows = list(perf_map.values())
    coverage_ratio = (len(rows) / len(universe)) if universe else 0.0
    no_bars_count = sum(1 for r in issues_map.values() if r == "no_bars")
    insufficient_history_count = sum(1 for r in issues_map.values() if r == "insufficient_history")
    perf_invalid_count = sum(1 for r in issues_map.values() if r == "perf_invalid")

    if not rows:
        storage.save_stock_rs_snapshot(snapshot_date, [])
        storage.save_stock_watchlist(snapshot_date, [])
        storage.save_stock_rs_issues(snapshot_date, issues_map)
        storage.save_stock_rs_meta(
            snapshot_date,
            {
                "universe_count": len(universe),
                "computed_count": 0,
                "no_bars_count": no_bars_count,
                "insufficient_history_count": insufficient_history_count,
                "perf_invalid_count": perf_invalid_count,
                "coverage_ratio": coverage_ratio,
            },
        )
        return {
            "snapshot_date": snapshot_date,
            "universe_count": len(universe),
            "attempted_count": len(target_symbols),
            "computed_count": 0,
            "watchlist_count": 0,
            "no_bars_count": no_bars_count,
            "insufficient_history_count": insufficient_history_count,
            "perf_invalid_count": perf_invalid_count,
            "coverage_ratio": coverage_ratio,
            "worker_errors": worker_errors,
        }

    ranks = {tf: _rank_by_key(rows, PERF_KEY_MAP[tf]) for tf in TIMEFRAMES}
    total = len(rows)
    weights = config.get("_normalized_weights") or {
        "week": 0.05,
        "month": 0.3,
        "quarter": 0.4,
        "half": 0.2,
        "year": 0.05,
    }

    for row in rows:
        row["rank_w"] = ranks["week"][row["symbol"]]
        row["rank_m"] = ranks["month"][row["symbol"]]
        row["rank_q"] = ranks["quarter"][row["symbol"]]
        row["rank_h"] = ranks["half"][row["symbol"]]
        row["rank_y"] = ranks["year"][row["symbol"]]
        row["rs_score"] = sum(
            weights[tf] * _percentile(ranks[tf][row["symbol"]], total) for tf in TIMEFRAMES
        )
        if row["rs_score"] >= tier_a:
            row["tier"] = "A"
        elif row["rs_score"] >= tier_b:
            row["tier"] = "B"
        else:
            row["tier"] = "C"

    rows.sort(key=lambda x: (-x["rs_score"], x["rank_m"], x["symbol"]))
    storage.save_stock_rs_snapshot(snapshot_date, rows)
    storage.save_stock_rs_issues(snapshot_date, issues_map)

    top_industries = filter_top_strong(scored_industries, config)
    top_keys = {item.key for item in top_industries}
    picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    symbol_to_industries: dict[str, list[str]] = {}
    for key, payload in picks.items():
        if key not in top_keys:
            continue
        for symbol in payload.get("tickers", []):
            symbol_to_industries.setdefault(symbol.upper(), []).append(key)

    cutoff = max(1, int(total * cross_top_percent))
    watch_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[:cutoff], start=1):
        industries = symbol_to_industries.get(row["symbol"], [])
        if not industries:
            continue
        watch_rows.append(
            {
                "symbol": row["symbol"],
                "rs_score": row["rs_score"],
                "rs_rank": idx,
                "industries": sorted(industries),
            }
        )
    storage.save_stock_watchlist(snapshot_date, watch_rows)
    storage.save_stock_rs_meta(
        snapshot_date,
        {
            "universe_count": len(universe),
            "computed_count": total,
            "no_bars_count": no_bars_count,
            "insufficient_history_count": insufficient_history_count,
            "perf_invalid_count": perf_invalid_count,
            "coverage_ratio": coverage_ratio,
        },
    )

    return {
        "snapshot_date": snapshot_date,
        "universe_count": len(universe),
        "attempted_count": len(target_symbols),
        "computed_count": total,
        "watchlist_count": len(watch_rows),
        "no_bars_count": no_bars_count,
        "insufficient_history_count": insufficient_history_count,
        "perf_invalid_count": perf_invalid_count,
        "coverage_ratio": coverage_ratio,
        "worker_errors": worker_errors,
    }
