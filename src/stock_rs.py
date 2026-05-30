"""Compute US stock relative strength (RS) from free sources."""

from __future__ import annotations

import csv
import ftplib
import io
import threading
import time
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

THREE_Q_OFFSET = 189
NEW_STOCK_MIN_BARS = 22

# 新股分档：互斥，仅 bar_count < min_price_rows（默认 260）
NEW_STOCK_COHORTS: dict[str, dict[str, Any]] = {
    "M": {"min_bars": 22, "max_bars": 63, "timeframes": ("week", "month")},
    "Q": {"min_bars": 63, "max_bars": 126, "timeframes": ("week", "month", "quarter")},
    "H": {"min_bars": 126, "max_bars": 189, "timeframes": ("week", "month", "quarter", "half")},
    "3Q": {
        "min_bars": 189,
        "max_bars": 260,
        "timeframes": ("week", "month", "quarter", "half", "three_q"),
    },
}


def _perf_key_for_timeframe(tf: str) -> str:
    if tf == "three_q":
        return "perf_tq"
    return PERF_KEY_MAP[tf]


RANK_KEY_MAP = {
    "week": "rank_w",
    "month": "rank_m",
    "quarter": "rank_q",
    "half": "rank_h",
    "three_q": "rank_tq",
}


def _rank_key_for_timeframe(tf: str) -> str:
    return RANK_KEY_MAP[tf]


def classify_new_stock_cohort(bar_count: int, min_main_rows: int) -> str | None:
    if bar_count >= min_main_rows or bar_count < NEW_STOCK_MIN_BARS:
        return None
    for cohort, spec in NEW_STOCK_COHORTS.items():
        if spec["min_bars"] <= bar_count < spec["max_bars"]:
            return cohort
    return None


def _top_industries_with_picks(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
) -> list[ScoredIndustry]:
    picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    return filter_top_strong(scored, config, stock_picks=picks)


def _offsets_for_cohort(cohort: str) -> dict[str, int]:
    spec = NEW_STOCK_COHORTS[cohort]
    offsets: dict[str, int] = {}
    for tf in spec["timeframes"]:
        if tf == "three_q":
            offsets[tf] = THREE_Q_OFFSET
        else:
            offsets[tf] = PERF_INDEX_OFFSETS[tf]
    return offsets


def _calc_performance_for_cohort(bars: list[dict[str, Any]], cohort: str) -> dict[str, float] | None:
    offsets = _offsets_for_cohort(cohort)
    need = max(offsets.values()) + 1
    if len(bars) < need:
        return None
    closes = [float(bar["close"]) for bar in bars]
    last = closes[-1]
    if last <= 0:
        return None
    result: dict[str, float] = {}
    for tf, offset in offsets.items():
        prev = closes[-1 - offset]
        if prev <= 0:
            return None
        result[_perf_key_for_timeframe(tf)] = (last / prev - 1.0) * 100.0
    return result


def _normalized_weights_for_timeframes(
    config: dict[str, Any],
    timeframes: tuple[str, ...],
) -> dict[str, float]:
    base = config.get("_normalized_weights") or {
        "week": 0.05,
        "month": 0.3,
        "quarter": 0.4,
        "half": 0.2,
        "year": 0.05,
    }
    weight_map = {
        "week": base["week"],
        "month": base["month"],
        "quarter": base["quarter"],
        "half": base["half"],
        "three_q": base["year"],
    }
    picked = {tf: float(weight_map[tf]) for tf in timeframes}
    total = sum(picked.values())
    if total <= 0:
        n = len(timeframes)
        return {tf: 1.0 / n for tf in timeframes}
    return {tf: v / total for tf, v in picked.items()}


def _score_new_stock_rows(
    rows: list[dict[str, Any]],
    cohort: str,
    config: dict[str, Any],
    tier_a: float,
    tier_b: float,
) -> None:
    timeframes = NEW_STOCK_COHORTS[cohort]["timeframes"]
    weights = _normalized_weights_for_timeframes(config, timeframes)
    ranks = {
        tf: _rank_by_key(rows, _perf_key_for_timeframe(tf)) for tf in timeframes
    }
    total = len(rows)
    for row in rows:
        for tf in timeframes:
            rk = _rank_key_for_timeframe(tf)
            row[rk] = ranks[tf][row["symbol"]]
        row["rs_score"] = sum(
            weights[tf] * _percentile(ranks[tf][row["symbol"]], total) for tf in timeframes
        )
        if row["rs_score"] >= tier_a:
            row["tier"] = "A"
        elif row["rs_score"] >= tier_b:
            row["tier"] = "B"
        else:
            row["tier"] = "C"


def _industry_pick_map(
    storage: Storage,
    snapshot_date: str,
    top_keys: set[str],
) -> dict[str, list[str]]:
    picks = storage.get_stock_picks_for_snapshot(snapshot_date)
    symbol_to_industries: dict[str, list[str]] = {}
    for key, payload in picks.items():
        if key not in top_keys:
            continue
        for symbol in payload.get("tickers", []):
            symbol_to_industries.setdefault(symbol.upper(), []).append(key)
    return symbol_to_industries


def _cross_watchlist_candidates(
    ranked_rows: list[dict[str, Any]],
    symbol_to_industries: dict[str, list[str]],
    cross_top_percent: float,
) -> list[dict[str, Any]]:
    if not ranked_rows:
        return []
    cutoff = max(1, int(len(ranked_rows) * cross_top_percent))
    out: list[dict[str, Any]] = []
    for row in ranked_rows[:cutoff]:
        industries = symbol_to_industries.get(row["symbol"], [])
        if not industries:
            continue
        out.append(
            {
                "symbol": row["symbol"],
                "rs_score": float(row["rs_score"]),
                "industries": sorted(industries),
            }
        )
    return out


def _merge_watchlists(
    main_candidates: list[dict[str, Any]],
    new_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for row in main_candidates:
        by_symbol[row["symbol"]] = row
    for row in new_candidates:
        if row["symbol"] in by_symbol:
            continue
        by_symbol[row["symbol"]] = row
    merged = sorted(
        by_symbol.values(),
        key=lambda x: (-x["rs_score"], x["symbol"]),
    )
    for idx, row in enumerate(merged, start=1):
        row["rs_rank"] = idx
    return merged


def backfill_new_stock_rs_for_snapshot(
    storage: Storage,
    snapshot_date: str,
    config: dict[str, Any],
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """仅对 insufficient_history 股票拉价并计算新股 RS，再与主 RS 观察名单合并。"""
    rs_cfg = config.get("stock_rs", {})
    min_price_rows = int(rs_cfg.get("min_price_rows", 260))
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    cross_top_percent = max(0.01, min(1.0, cross_top_percent))
    max_workers = max(4, min(64, int(rs_cfg.get("max_workers", 24))))
    request_timeout = int(rs_cfg.get("request_timeout_seconds", 20))
    prefer_stooq = bool(rs_cfg.get("prefer_stooq", False))

    issues = storage.get_stock_rs_issues(snapshot_date)
    symbols = sorted(s for s, r in issues.items() if r == "insufficient_history")
    insufficient_bars: dict[str, list[dict[str, Any]]] = {}
    user_agent = "Mozilla/5.0"
    total = len(symbols)
    processed = 0
    if progress_callback:
        progress_callback(0, total)

    def _fetch_one(symbol: str) -> tuple[str, list[dict[str, Any]]]:
        with requests.Session() as session:
            session.headers.update({"User-Agent": user_agent})
            bars: list[dict[str, Any]] = []
            if prefer_stooq:
                bars = fetch_stooq_daily_bars(symbol, session, timeout=request_timeout)
            if not bars:
                bars = fetch_yahoo_daily_bars(symbol, session, timeout=request_timeout)
        return symbol, bars

    if symbols:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_one, symbol) for symbol in symbols]
            for future in as_completed(futures):
                symbol, bars = future.result()
                if bars and len(bars) < min_price_rows:
                    insufficient_bars[symbol] = bars
                processed += 1
                if progress_callback and (processed % 20 == 0 or processed == total):
                    progress_callback(processed, total)
    elif progress_callback:
        progress_callback(0, 0)

    scored_rows = storage.get_snapshot(snapshot_date)

    class _Industry:
        def __init__(self, d: dict[str, Any]):
            self.key = d["industry_key"]
            self.name = d["name"]
            self.score = float(d.get("score") or 0)
            self.rank_m = int(d.get("rank_m") or 9999)
            self.rank_q = int(d.get("rank_q") or 9999)
            self.excluded = bool(d.get("excluded"))

    scored = [_Industry(r) for r in scored_rows if not r.get("excluded")]
    new_stock_result = compute_and_store_new_stock_rs(
        storage,
        snapshot_date,
        insufficient_bars,
        config,
        min_price_rows,
        cross_top_percent,
        scored,
    )

    main_rows = storage.get_stock_rs_raw(snapshot_date)
    top_industries = _top_industries_with_picks(storage, snapshot_date, scored, config)
    top_keys = {item.key for item in top_industries}
    symbol_to_industries = _industry_pick_map(storage, snapshot_date, top_keys)
    main_watch = _cross_watchlist_candidates(main_rows, symbol_to_industries, cross_top_percent)
    watch_rows = _merge_watchlists(main_watch, new_stock_result["new_watch_candidates"])
    storage.save_stock_watchlist(snapshot_date, watch_rows)

    prev_meta = storage.get_stock_rs_meta(snapshot_date) or {}
    storage.save_stock_rs_meta(
        snapshot_date,
        {
            "universe_count": int(prev_meta.get("universe_count", 0)),
            "computed_count": int(prev_meta.get("computed_count", 0)),
            "no_bars_count": int(prev_meta.get("no_bars_count", 0)),
            "insufficient_history_count": int(prev_meta.get("insufficient_history_count", 0)),
            "perf_invalid_count": int(prev_meta.get("perf_invalid_count", 0)),
            "coverage_ratio": float(prev_meta.get("coverage_ratio", 0.0)),
            "new_stock_m_count": new_stock_result["new_stock_m_count"],
            "new_stock_q_count": new_stock_result["new_stock_q_count"],
            "new_stock_h_count": new_stock_result["new_stock_h_count"],
            "new_stock_3q_count": new_stock_result["new_stock_3q_count"],
            "new_stock_leaderboard_count": new_stock_result["new_stock_leaderboard_count"],
            "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
        },
    )

    return {
        **new_stock_result,
        "fetched_symbols": len(symbols),
        "bars_for_new_rs": len(insufficient_bars),
        "watchlist_count": len(watch_rows),
    }


def compute_and_store_new_stock_rs(
    storage: Storage,
    snapshot_date: str,
    insufficient_bars: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
    min_price_rows: int,
    cross_top_percent: float,
    scored_industries: list[ScoredIndustry],
) -> dict[str, Any]:
    rs_cfg = config.get("stock_rs", {})
    tier_a = float(rs_cfg.get("tier_a_score", 0.8))
    tier_b = float(rs_cfg.get("tier_b_score", 0.65))
    if not bool(rs_cfg.get("new_stock_enabled", True)):
        return {
            "new_stock_m_count": 0,
            "new_stock_q_count": 0,
            "new_stock_h_count": 0,
            "new_stock_3q_count": 0,
            "new_stock_leaderboard_count": 0,
            "new_stock_rows": [],
            "new_watch_candidates": [],
        }

    cohort_rows: dict[str, list[dict[str, Any]]] = {k: [] for k in NEW_STOCK_COHORTS}
    for symbol, bars in insufficient_bars.items():
        cohort = classify_new_stock_cohort(len(bars), min_price_rows)
        if not cohort:
            continue
        perf = _calc_performance_for_cohort(bars, cohort)
        if not perf:
            continue
        row: dict[str, Any] = {
            "symbol": symbol,
            "cohort": cohort,
            "bar_count": len(bars),
            "in_leaderboard": False,
        }
        row.update(perf)
        cohort_rows[cohort].append(row)

    counts = {c: len(cohort_rows[c]) for c in NEW_STOCK_COHORTS}
    all_scored: list[dict[str, Any]] = []
    leaderboard: list[dict[str, Any]] = []

    for cohort, rows in cohort_rows.items():
        if not rows:
            continue
        _score_new_stock_rows(rows, cohort, config, tier_a, tier_b)
        rows.sort(key=lambda x: (-x["rs_score"], x["symbol"]))
        cutoff = max(1, int(len(rows) * cross_top_percent))
        for row in rows:
            row["in_leaderboard"] = False
        for row in rows[:cutoff]:
            row["in_leaderboard"] = True
            leaderboard.append(row)
        all_scored.extend(rows)

    top_industries = _top_industries_with_picks(storage, snapshot_date, scored_industries, config)
    top_keys = {item.key for item in top_industries}
    symbol_to_industries = _industry_pick_map(storage, snapshot_date, top_keys)
    new_watch = _cross_watchlist_candidates(leaderboard, symbol_to_industries, 1.0)

    storage.save_stock_rs_new_snapshot(snapshot_date, all_scored)
    return {
        "new_stock_m_count": counts["M"],
        "new_stock_q_count": counts["Q"],
        "new_stock_h_count": counts["H"],
        "new_stock_3q_count": counts["3Q"],
        "new_stock_leaderboard_count": len(leaderboard),
        "new_stock_rows": all_scored,
        "new_watch_candidates": new_watch,
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


def load_us_universe_with_cache(storage: Storage, config: dict[str, Any]) -> list[dict[str, Any]]:
    rs_cfg = config.get("stock_rs", {})
    cache_hours = int(rs_cfg.get("universe_cache_hours", 24))
    universe_cap = int(rs_cfg.get("universe_cap", 0))

    freshness = storage.get_stock_universe_freshness()
    count = storage.count_stock_universe()
    updated_at_raw = freshness.get("updated_at") if freshness else None
    if count > 500 and updated_at_raw:
        try:
            updated_at = datetime.fromisoformat(str(updated_at_raw))
            age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600.0
            if age_hours <= cache_hours:
                rows = storage.list_stock_universe()
                return rows[:universe_cap] if universe_cap > 0 else rows
        except ValueError:
            pass

    universe = load_us_universe_from_nasdaq()
    if universe_cap > 0:
        universe = universe[:universe_cap]
    storage.upsert_stock_universe(universe, source="nasdaqtrader")
    return universe


def _symbol_payload_from_bars(
    symbol: str,
    bars: list[dict[str, Any]],
    *,
    min_price_rows: int,
    source: str,
) -> dict[str, Any]:
    if not bars:
        return {"symbol": symbol, "status": "no_bars", "reason": "no_bars"}
    if len(bars) < min_price_rows:
        return {
            "symbol": symbol,
            "status": "insufficient_history",
            "reason": "insufficient_history",
            "bars": bars,
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


def _rs_meta_payload(
    *,
    universe_count: int,
    computed_count: int,
    no_bars_count: int,
    insufficient_history_count: int,
    perf_invalid_count: int,
    coverage_ratio: float,
    new_stock_result: dict[str, Any] | None = None,
    worker_errors: list[str] | None = None,
) -> dict[str, Any]:
    new_stock_result = new_stock_result or {}
    return {
        "universe_count": universe_count,
        "computed_count": computed_count,
        "no_bars_count": no_bars_count,
        "insufficient_history_count": insufficient_history_count,
        "perf_invalid_count": perf_invalid_count,
        "coverage_ratio": coverage_ratio,
        "new_stock_m_count": int(new_stock_result.get("new_stock_m_count", 0) or 0),
        "new_stock_q_count": int(new_stock_result.get("new_stock_q_count", 0) or 0),
        "new_stock_h_count": int(new_stock_result.get("new_stock_h_count", 0) or 0),
        "new_stock_3q_count": int(new_stock_result.get("new_stock_3q_count", 0) or 0),
        "new_stock_leaderboard_count": int(
            new_stock_result.get("new_stock_leaderboard_count", 0) or 0
        ),
        "new_stock_watchlist_added": int(
            new_stock_result.get("new_stock_watchlist_added", 0) or 0
        ),
        "worker_error_count": len(worker_errors or []),
        "worker_error_sample": (worker_errors or [])[:3],
    }


def _apply_symbol_payload(
    payload: dict[str, Any],
    *,
    storage: Storage,
    snapshot_date: str,
    perf_map: dict[str, dict[str, Any]],
    issues_map: dict[str, str],
    insufficient_bars: dict[str, list[dict[str, Any]]],
    save_price_history: bool,
) -> None:
    status = payload.get("status")
    symbol = str(payload.get("symbol") or "")
    if not symbol:
        return
    if status == "ok":
        if save_price_history:
            storage.replace_stock_price_history(
                symbol,
                payload["bars"],
                source=payload.get("source", "yahoo"),
            )
        perf_map[symbol] = {"symbol": symbol, **payload["perf"]}
        issues_map.pop(symbol, None)
        return
    reason = str(payload.get("reason") or "no_bars")
    issues_map[symbol] = reason
    if reason == "insufficient_history" and payload.get("bars"):
        insufficient_bars[symbol] = payload["bars"]


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


def _yahoo_rs_batches(symbols: list[str], batch_size: int) -> list[list[str]]:
    return [symbols[i : i + batch_size] for i in range(0, len(symbols), batch_size)]


def _fetch_yahoo_batch_with_retry(
    batch: list[str],
    *,
    request_timeout: int,
    user_agent: str,
    retry_pause_seconds: float = 0.8,
) -> dict[str, list[dict[str, Any]]]:
    if not batch:
        return {}
    with requests.Session() as session:
        session.headers.update({"User-Agent": user_agent})
        bars_map = fetch_yahoo_batch_daily_bars(batch, session, timeout=request_timeout)
    if bars_map:
        return bars_map
    time.sleep(retry_pause_seconds)
    with requests.Session() as session:
        session.headers.update({"User-Agent": user_agent})
        return fetch_yahoo_batch_daily_bars(batch, session, timeout=request_timeout)


def _run_yahoo_batch_rs_fetch(
    *,
    target_symbols: list[str],
    yahoo_batch_size: int,
    yahoo_batch_workers: int,
    request_timeout: int,
    user_agent: str,
    storage: Storage,
    snapshot_date: str,
    min_price_rows: int,
    perf_map: dict[str, dict[str, Any]],
    issues_map: dict[str, str],
    insufficient_bars: dict[str, list[dict[str, Any]]],
    save_price_history: bool,
    progress_callback: Callable[[int, int], None] | None,
) -> None:
    batches = _yahoo_rs_batches(target_symbols, yahoo_batch_size)
    total_symbols = len(target_symbols)
    processed = 0
    apply_lock = threading.Lock()

    def _process_batch(batch: list[str]) -> None:
        nonlocal processed
        bars_map = _fetch_yahoo_batch_with_retry(
            batch,
            request_timeout=request_timeout,
            user_agent=user_agent,
        )
        with apply_lock:
            for symbol in batch:
                payload = _symbol_payload_from_bars(
                    symbol,
                    bars_map.get(symbol, []),
                    min_price_rows=min_price_rows,
                    source="yahoo",
                )
                _apply_symbol_payload(
                    payload,
                    storage=storage,
                    snapshot_date=snapshot_date,
                    perf_map=perf_map,
                    issues_map=issues_map,
                    insufficient_bars=insufficient_bars,
                    save_price_history=save_price_history,
                )
            processed += len(batch)
            if progress_callback and (processed % 25 == 0 or processed >= total_symbols):
                progress_callback(processed, total_symbols)

    workers = max(1, min(yahoo_batch_workers, len(batches)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_process_batch, batches))


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
    *,
    force_full: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    rs_cfg = config.get("stock_rs", {})
    request_timeout = int(rs_cfg.get("request_timeout_seconds", 20))
    min_price_rows = int(rs_cfg.get("min_price_rows", 260))
    max_workers = int(rs_cfg.get("max_workers", 24))
    max_workers = max(4, min(64, max_workers))
    save_price_history = bool(rs_cfg.get("save_price_history", False))
    incremental_mode = bool(rs_cfg.get("incremental_mode", True)) and (not force_full)
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    cross_top_percent = max(0.01, min(1.0, cross_top_percent))
    tier_a = float(rs_cfg.get("tier_a_score", 0.8))
    tier_b = float(rs_cfg.get("tier_b_score", 0.65))
    prefer_stooq = bool(rs_cfg.get("prefer_stooq", False))
    yahoo_batch_size = int(rs_cfg.get("yahoo_batch_size", 20))
    yahoo_batch_size = max(5, min(50, yahoo_batch_size))
    yahoo_batch_workers = int(rs_cfg.get("yahoo_batch_workers", 6))
    yahoo_batch_workers = max(1, min(12, yahoo_batch_workers))

    universe = load_us_universe_with_cache(storage, config)
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
    insufficient_bars: dict[str, list[dict[str, Any]]] = {}

    worker_errors: list[str] = []

    user_agent = "Mozilla/5.0"
    total_symbols = len(target_symbols)
    processed = 0
    if progress_callback:
        progress_callback(0, total_symbols)

    def _fetch_one_stooq(symbol: str) -> dict[str, Any]:
        with requests.Session() as session:
            session.headers.update({"User-Agent": user_agent})
            bars = fetch_stooq_daily_bars(symbol, session, timeout=request_timeout)
            source = "stooq"
            if not bars:
                bars = fetch_yahoo_daily_bars(symbol, session, timeout=request_timeout)
                source = "yahoo"
        return _symbol_payload_from_bars(
            symbol,
            bars,
            min_price_rows=min_price_rows,
            source=source,
        )

    if target_symbols:
        if prefer_stooq:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(_fetch_one_stooq, symbol): symbol for symbol in target_symbols
                }
                for future in as_completed(future_map):
                    symbol = future_map[future]
                    try:
                        payload = future.result()
                    except Exception as exc:  # noqa: BLE001
                        if len(worker_errors) < 20:
                            worker_errors.append(f"{symbol}: {exc}")
                        payload = {"symbol": symbol, "status": "no_bars", "reason": "no_bars"}
                    _apply_symbol_payload(
                        payload,
                        storage=storage,
                        snapshot_date=snapshot_date,
                        perf_map=perf_map,
                        issues_map=issues_map,
                        insufficient_bars=insufficient_bars,
                        save_price_history=save_price_history,
                    )
                    processed += 1
                    if progress_callback and (processed % 25 == 0 or processed == total_symbols):
                        progress_callback(processed, total_symbols)
        else:
            _run_yahoo_batch_rs_fetch(
                target_symbols=target_symbols,
                yahoo_batch_size=yahoo_batch_size,
                yahoo_batch_workers=yahoo_batch_workers,
                request_timeout=request_timeout,
                user_agent=user_agent,
                storage=storage,
                snapshot_date=snapshot_date,
                min_price_rows=min_price_rows,
                perf_map=perf_map,
                issues_map=issues_map,
                insufficient_bars=insufficient_bars,
                save_price_history=save_price_history,
                progress_callback=progress_callback,
            )
    elif progress_callback:
        progress_callback(0, 0)

    rows = list(perf_map.values())
    coverage_ratio = (len(rows) / len(universe)) if universe else 0.0
    no_bars_count = sum(1 for r in issues_map.values() if r == "no_bars")
    insufficient_history_count = sum(1 for r in issues_map.values() if r == "insufficient_history")
    perf_invalid_count = sum(1 for r in issues_map.values() if r == "perf_invalid")

    if not rows:
        if incremental_mode and existing_rows:
            storage.save_stock_rs_issues(snapshot_date, issues_map)
            prev_meta = storage.get_stock_rs_meta(snapshot_date) or {}
            preserved_count = len(existing_rows)
            return {
                "snapshot_date": snapshot_date,
                "universe_count": len(universe),
                "attempted_count": len(target_symbols),
                "computed_count": preserved_count,
                "watchlist_count": storage.count_stock_watchlist(snapshot_date),
                "no_bars_count": no_bars_count,
                "insufficient_history_count": insufficient_history_count,
                "perf_invalid_count": perf_invalid_count,
                "coverage_ratio": float(prev_meta.get("coverage_ratio", 0.0)),
                "new_stock_leaderboard_count": int(
                    prev_meta.get("new_stock_leaderboard_count", 0) or 0
                ),
                "new_stock_watchlist_added": int(
                    prev_meta.get("new_stock_watchlist_added", 0) or 0
                ),
                "worker_errors": worker_errors,
                "preserved_existing_rs": True,
            }

        # 全量或无历史时，如果所有目标股票都 no_bars，视为上游行情源不可用，交给任务层报错重试
        if target_symbols and no_bars_count >= len(target_symbols):
            raise RuntimeError(
                "RS 计算失败：行情源返回空数据（no_bars 全量命中）。"
                "请检查网络/代理，或稍后重试。"
            )

        storage.save_stock_rs_snapshot(snapshot_date, [])
        storage.save_stock_rs_issues(snapshot_date, issues_map)
        new_stock_result = compute_and_store_new_stock_rs(
            storage,
            snapshot_date,
            insufficient_bars,
            config,
            min_price_rows,
            cross_top_percent,
            scored_industries,
        )
        watch_rows = _merge_watchlists([], new_stock_result["new_watch_candidates"])
        storage.save_stock_watchlist(snapshot_date, watch_rows)
        storage.save_stock_rs_meta(
            snapshot_date,
            _rs_meta_payload(
                universe_count=len(universe),
                computed_count=0,
                no_bars_count=no_bars_count,
                insufficient_history_count=insufficient_history_count,
                perf_invalid_count=perf_invalid_count,
                coverage_ratio=coverage_ratio,
                new_stock_result={
                    **new_stock_result,
                    "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
                },
                worker_errors=worker_errors,
            ),
        )
        return {
            "snapshot_date": snapshot_date,
            "universe_count": len(universe),
            "attempted_count": len(target_symbols),
            "computed_count": 0,
            "watchlist_count": len(watch_rows),
            "no_bars_count": no_bars_count,
            "insufficient_history_count": insufficient_history_count,
            "perf_invalid_count": perf_invalid_count,
            "coverage_ratio": coverage_ratio,
            "new_stock_leaderboard_count": new_stock_result["new_stock_leaderboard_count"],
            "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
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

    top_industries = _top_industries_with_picks(storage, snapshot_date, scored_industries, config)
    top_keys = {item.key for item in top_industries}
    symbol_to_industries = _industry_pick_map(storage, snapshot_date, top_keys)

    main_watch_candidates = _cross_watchlist_candidates(rows, symbol_to_industries, cross_top_percent)
    new_stock_result = compute_and_store_new_stock_rs(
        storage,
        snapshot_date,
        insufficient_bars,
        config,
        min_price_rows,
        cross_top_percent,
        scored_industries,
    )
    watch_rows = _merge_watchlists(main_watch_candidates, new_stock_result["new_watch_candidates"])
    storage.save_stock_watchlist(snapshot_date, watch_rows)
    storage.save_stock_rs_meta(
        snapshot_date,
        _rs_meta_payload(
            universe_count=len(universe),
            computed_count=total,
            no_bars_count=no_bars_count,
            insufficient_history_count=insufficient_history_count,
            perf_invalid_count=perf_invalid_count,
            coverage_ratio=coverage_ratio,
            new_stock_result={
                **new_stock_result,
                "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
            },
            worker_errors=worker_errors,
        ),
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
        "new_stock_leaderboard_count": new_stock_result["new_stock_leaderboard_count"],
        "new_stock_watchlist_added": len(new_stock_result["new_watch_candidates"]),
        "worker_errors": worker_errors,
        "worker_error_count": len(worker_errors),
    }


def rebuild_stock_watchlist_for_snapshot(
    storage: Storage,
    snapshot_date: str,
    scored_industries: list[ScoredIndustry],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild cross watchlist from existing RS rows and latest industry stock picks."""
    rs_cfg = config.get("stock_rs", {})
    cross_top_percent = float(rs_cfg.get("cross_top_percent", 0.1))
    cross_top_percent = max(0.01, min(1.0, cross_top_percent))

    rows = storage.get_stock_rs_raw(snapshot_date)
    if not rows:
        return {
            "snapshot_date": snapshot_date,
            "watchlist_count": 0,
            "skipped": True,
            "reason": "no_rs_rows",
        }

    top_industries = _top_industries_with_picks(storage, snapshot_date, scored_industries, config)
    top_keys = {item.key for item in top_industries}
    symbol_to_industries = _industry_pick_map(storage, snapshot_date, top_keys)

    main_watch = _cross_watchlist_candidates(rows, symbol_to_industries, cross_top_percent)

    leaderboard = storage.get_stock_rs_new(
        snapshot_date,
        leaderboard_only=True,
        limit=5000,
    )
    new_watch_rows = [
        {"symbol": row["symbol"], "rs_score": float(row["rs_score"])}
        for row in leaderboard
    ]
    new_watch = _cross_watchlist_candidates(new_watch_rows, symbol_to_industries, 1.0)

    watch_rows = _merge_watchlists(main_watch, new_watch)
    storage.save_stock_watchlist(snapshot_date, watch_rows)

    meta = storage.get_stock_rs_meta(snapshot_date)
    if meta:
        updated = dict(meta)
        updated["new_stock_watchlist_added"] = len(new_watch)
        storage.save_stock_rs_meta(snapshot_date, updated)

    return {
        "snapshot_date": snapshot_date,
        "watchlist_count": len(watch_rows),
        "top_industry_count": len(top_keys),
        "skipped": False,
    }
