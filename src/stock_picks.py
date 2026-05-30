"""Fetch and cache filtered stock picks for industries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import time
from typing import Any

from src.finviz_stock_screener import (
    build_screener_filters,
    build_screener_url,
    fetch_industry_tickers,
    prepare_finviz_session,
)
from src.scoring import ScoredIndustry, top_strong_sort_key
from src.storage import Storage


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
        if current and current.get("tickers"):
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
    max_workers = int(scraper_cfg.get("stock_pick_workers", 3))
    max_workers = max(1, min(6, max_workers))

    shared_session, session_lock = prepare_finviz_session(config)

    def _fetch_one(key: str, cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        try:
            payload = fetch_industry_tickers(
                key,
                cfg,
                session=shared_session,
                session_lock=session_lock,
                skip_warmup=True,
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
            payload = _save_pick_failure_with_stale_fallback(
                storage,
                snapshot_date,
                key,
                cfg,
                exc,
            )
            return key, payload

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_one, key, config) for key in industry_keys]
            for future in as_completed(futures):
                key, payload = future.result()
                results[key] = payload
    finally:
        if shared_session is not None:
            shared_session.close()

    # 动态限速回补：若出现 Cloudflare/连接类错误，则降并发+增延时重试失败行业。
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


def fetch_top_industry_stock_picks(
    storage: Storage,
    snapshot_date: str,
    scored: list[ScoredIndustry],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    active = [s for s in scored if not s.excluded]
    active.sort(key=lambda x: top_strong_sort_key(x.score, x.rank_m, x.rank_q, x.key))
    candidate_count = min(len(active), max(top_n * 3, top_n + 15))
    keys = [item.key for item in active[:candidate_count]]
    if not keys:
        return {}
    return fetch_and_store_stock_picks(storage, snapshot_date, keys, config)
