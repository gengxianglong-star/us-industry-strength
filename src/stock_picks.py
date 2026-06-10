"""Fetch and cache filtered stock picks for industries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import threading
import time
from typing import Any

from src.finviz_stock_screener import (
    build_screener_filters,
    build_screener_url,
    fetch_industry_tickers,
    open_playwright_session,
    prepare_finviz_session,
    use_playwright_scraper,
)
from src.logging_config import get_logger
from src.scoring import ScoredIndustry, top_strong_sort_key
from src.storage import Storage

logger = get_logger(__name__)


def _stale_fallback_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("scraper", {}).get("stale_fallback_enabled", True))


def _save_pick_failure_with_stale_fallback(
    storage: Storage,
    snapshot_date: str,
    industry_key: str,
    config: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    filters = build_screener_filters(industry_key, config)
    screener_url = build_screener_url(industry_key, config, 1)
    err_text = str(exc)

    stale_row: dict[str, Any] | None = None
    stale_from: str | None = None
    if _stale_fallback_enabled(config):
        current = storage.get_industry_stock_picks(snapshot_date, industry_key)
        if current and current.get("tickers") and not str(current.get("error") or "").strip():
            stale_row = current
            stale_from = snapshot_date
        else:
            stale_row = storage.get_latest_successful_industry_stock_picks(
                industry_key,
                before_snapshot_date=snapshot_date,
            )
            if stale_row:
                stale_from = str(stale_row.get("snapshot_date") or "")

    if stale_row and stale_row.get("tickers"):
        error = f"沿用缓存({stale_from}): {err_text}"
        tickers = list(stale_row["tickers"])
        storage.save_industry_stock_picks(
            snapshot_date,
            industry_key,
            tickers,
            str(stale_row.get("screener_url") or screener_url),
            str(stale_row.get("filters") or filters),
            error=error,
        )
        return {
            "industry_key": industry_key,
            "tickers": tickers,
            "ticker_count": len(tickers),
            "error": error,
            "screener_url": str(stale_row.get("screener_url") or screener_url),
            "filters": str(stale_row.get("filters") or filters),
            "stale_fallback": True,
            "stale_from_snapshot_date": stale_from,
        }

    storage.save_industry_stock_picks(
        snapshot_date,
        industry_key,
        [],
        screener_url,
        filters,
        error=err_text,
    )
    return {
        "industry_key": industry_key,
        "tickers": [],
        "error": err_text,
        "screener_url": screener_url,
        "filters": filters,
        "stale_fallback": False,
    }


def fetch_and_store_stock_picks(
    storage: Storage,
    snapshot_date: str,
    industry_keys: list[str],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not industry_keys:
        return results

    scraper_cfg = config.get("scraper", {})
    playwright_mode = use_playwright_scraper(config)
    max_workers = 1 if playwright_mode else int(scraper_cfg.get("stock_pick_workers", 3))
    max_workers = max(1, min(6, max_workers))

    shared_session, session_lock = (None, threading.Lock())
    if not playwright_mode:
        shared_session, session_lock = prepare_finviz_session(config)

    def _fetch_one(
        key: str,
        cfg: dict[str, Any],
        *,
        playwright_session=None,
    ) -> tuple[str, dict[str, Any]]:
        try:
            payload = fetch_industry_tickers(
                key,
                cfg,
                session=shared_session,
                session_lock=session_lock,
                skip_warmup=True,
                playwright_session=playwright_session,
            )
            storage.save_industry_stock_picks(
                snapshot_date,
                key,
                payload["tickers"],
                payload["screener_url"],
                payload["filters"],
            )
            return key, payload
        except Exception as exc:  # noqa: BLE001 - persist error for UI
            logger.warning("stock pick failed for %s: %s", key, exc)
            payload = _save_pick_failure_with_stale_fallback(
                storage,
                snapshot_date,
                key,
                cfg,
                exc,
            )
            return key, payload

    def _run_http_workers() -> None:
        nonlocal shared_session, session_lock
        if shared_session is None:
            shared_session, session_lock = prepare_finviz_session(config)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_one, key, config) for key in industry_keys]
            for future in as_completed(futures):
                key, payload = future.result()
                results[key] = payload

    used_playwright = False
    try:
        if playwright_mode:
            try:
                with open_playwright_session(config) as playwright_session:
                    for key in industry_keys:
                        key, payload = _fetch_one(
                            key, config, playwright_session=playwright_session
                        )
                        results[key] = payload
                        time.sleep(float(scraper_cfg.get("request_delay_seconds", 1.5)))
                used_playwright = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Playwright unavailable (%s); falling back to curl/cookie HTTP",
                    exc,
                )
                _run_http_workers()
        else:
            _run_http_workers()
    finally:
        if shared_session is not None:
            shared_session.close()

    # 动态限速回补：若出现 Cloudflare/连接类错误，则降并发+增延时重试失败行业。
    if used_playwright:
        return results

    retry_keys: list[str] = []
    for key, payload in results.items():
        err = str(payload.get("error") or "").lower()
        if not err:
            continue
        if "cloudflare" in err or "timed out" in err or "ssl" in err or "connection" in err:
            retry_keys.append(key)
    if retry_keys:
        retry_cfg = deepcopy(config)
        scraper_cfg = retry_cfg.setdefault("scraper", {})
        scraper_cfg["stock_pick_workers"] = 1
        old_delay = float(scraper_cfg.get("request_delay_seconds", 1.5))
        scraper_cfg["request_delay_seconds"] = min(6.0, max(2.0, old_delay * 1.8))
        # 轻微错峰，降低连续请求触发风控的概率
        time.sleep(1.0)
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(_fetch_one, key, retry_cfg) for key in retry_keys]
            for future in as_completed(futures):
                key, payload = future.result()
                results[key] = payload

    return results


def build_and_store_elite_industry_picks(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
    *,
    elite_market: dict[str, dict[str, Any]] | None = None,
    per_industry_cap: int = 20,
) -> dict[str, dict[str, Any]]:
    """Pair Top industries with Elite symbols by industry name + RS rank (no screener crawl)."""
    from src.services.elite_data import fetch_elite_market_data

    market = elite_market or fetch_elite_market_data()
    if not market:
        return {}

    rs_map = {
        str(row["symbol"]).upper(): row for row in storage.get_stock_rs_raw(snapshot_date)
    }
    by_industry: dict[str, list[str]] = {}
    for sym, row in market.items():
        industry_name = str(row.get("industry") or "").strip().lower()
        if industry_name:
            by_industry.setdefault(industry_name, []).append(sym.upper())

    active = [item for item in scored if not item.excluded]
    active.sort(key=lambda item: top_strong_sort_key(item.score, item.rank_m, item.rank_q, item.key))
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    results: dict[str, dict[str, Any]] = {}
    filled = 0

    for item in active:
        if filled >= top_n:
            break
        candidates = by_industry.get(item.name.strip().lower(), [])
        ranked = [
            (sym, rs_map[sym])
            for sym in candidates
            if sym in rs_map
        ]
        ranked.sort(
            key=lambda pair: (-float(pair[1].get("rs_score", 0) or 0), pair[0]),
        )
        tickers = [sym for sym, _ in ranked[:per_industry_cap]]
        if not tickers:
            continue
        filters = "elite_industry_match"
        screener_url = "elite://export/local"
        storage.save_industry_stock_picks(
            snapshot_date,
            item.key,
            tickers,
            screener_url,
            filters,
        )
        results[item.key] = {
            "tickers": tickers,
            "screener_url": screener_url,
            "filters": filters,
            "elite_source": True,
        }
        filled += 1

    logger.info(
        "Elite industry picks: %d industries, %d tickers",
        len(results),
        sum(len(payload["tickers"]) for payload in results.values()),
    )
    return results


def fetch_top_industry_stock_picks(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Fetch screener hits until Top N slots are filled, scanning lower ranks as needed."""
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    active = [s for s in scored if not s.excluded]
    active.sort(key=lambda x: top_strong_sort_key(x.score, x.rank_m, x.rank_q, x.key))
    if not active:
        return {}

    batch_size = max(5, min(12, top_n))
    all_results: dict[str, dict[str, Any]] = {}
    filled_keys: list[str] = []
    pending: list[str] = []

    def _flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        batch_result = fetch_and_store_stock_picks(
            storage,
            snapshot_date,
            pending,
            config,
        )
        all_results.update(batch_result)
        for key in pending:
            if len(filled_keys) >= top_n:
                break
            tickers = (batch_result.get(key) or {}).get("tickers") or []
            if tickers:
                filled_keys.append(key)
        pending = []

    for item in active:
        if len(filled_keys) >= top_n:
            break
        pending.append(item.key)
        if len(pending) >= batch_size:
            _flush_pending()

    if pending and len(filled_keys) < top_n:
        _flush_pending()

    return all_results
