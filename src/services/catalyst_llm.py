"""AI-powered catalyst extraction for watchlist stocks via Finviz Elite + DeepSeek.

Uses ``FINVIZ_AUTH_KEY`` to fetch news from the Finviz Elite quote page
(direct, ad-free, no IP blocking), then extracts a Qullamaggie-style
bullish catalyst tag via DeepSeek (``deepseek-v4-flash``).
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from src.logging_config import get_logger
from src.services import deepseek_llm

logger = get_logger(__name__)

load_dotenv()

_FINVIZ_KEY: str | None = (
    os.environ.get("FINVIZ_AUTH_KEY") or os.environ.get("FINVIZ_ELITE_AUTH") or None
)

_ELITE_QUOTE_URL = "https://elite.finviz.com/quote.ashx"
_ELITE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_CATALYST_SLEEP_SEC = 1.0


def is_available() -> bool:
    """Return ``True`` if both DeepSeek API key and Finviz Elite key are set."""
    return deepseek_llm.is_available() and _FINVIZ_KEY is not None


def _fetch_news_via_elite(symbol: str, max_items: int = 4) -> list[str]:
    """Fetch recent news headlines from the Finviz Elite quote page."""
    if not _FINVIZ_KEY:
        logger.debug("FINVIZ_AUTH_KEY not set — skipping Elite news fetch for %s", symbol)
        return []

    url = f"{_ELITE_QUOTE_URL}?t={symbol}&auth={_FINVIZ_KEY}"
    try:
        resp = requests.get(url, headers=_ELITE_HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.warning(
                "Finviz Elite returned %d for %s news fetch",
                resp.status_code, symbol,
            )
            return []
    except requests.RequestException as exc:
        logger.warning("Finviz Elite news fetch failed for %s: %s", symbol, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    news_table = soup.find(id="news-table")
    if not news_table:
        logger.info("📭 %s — no news-table found on Elite quote page", symbol)
        return []

    headlines: list[str] = []
    for row in news_table.find_all("tr")[:max_items]:
        a_tag = row.find("a")
        if a_tag:
            text = a_tag.text.strip()
            if text:
                headlines.append(text)

    if headlines:
        logger.debug("  %s — %d headlines from Elite", symbol, len(headlines))
    return headlines


def extract_catalyst(symbol: str) -> dict[str, Any]:
    """Fetch recent news via Finviz Elite and use DeepSeek to extract a catalyst tag."""
    if not deepseek_llm.is_available():
        logger.debug("DeepSeek not available — skipping %s", symbol)
        return {}

    headlines = _fetch_news_via_elite(symbol)
    if not headlines:
        return {}

    prompt = (
        "You are a professional Swing Trader following Qullamaggie's Episodic Pivot strategy.\n"
        f"Review the following recent news headlines for stock ${symbol}.\n"
        "Extract the core bullish catalyst in MAX 4 WORDS "
        '(e.g., "EARNINGS BEAT", "FDA APPROVAL", "GUIDANCE RAISED", "NEW CONTRACT").\n'
        "If the news is purely negative, noise, or has no clear catalyst, "
        'return exactly the word: "NONE".\n'
        "\n"
        "Headlines:\n"
        + "\n".join(f"- {h}" for h in headlines)
        + "\n\nReturn ONLY the max 4-word tag. No explanation."
    )

    try:
        tag, model = deepseek_llm.chat(
            prompt,
            max_tokens=32,
            temperature=0.3,
            thinking="disabled",
        )
        tag = tag.strip().upper()

        if tag == "NONE" or len(tag) > 25 or not tag:
            logger.info("🤖 %s — AI tagged as noise (NONE)", symbol)
            return {}

        logger.info("✨ %s — catalyst: 【%s】 (%s)", symbol, tag, model)
        return {
            "tag": tag,
            "headlines": headlines[:2],
        }

    except Exception:
        logger.warning("DeepSeek catalyst extraction failed for %s", symbol, exc_info=True)
        return {}


def probe_catalyst_pipeline(test_symbol: str = "AAPL") -> dict[str, Any]:
    """Non-secret health check for Finviz Elite news + DeepSeek (used by CI/local)."""
    finviz_set = _FINVIZ_KEY is not None
    deepseek_set = deepseek_llm.is_available()
    result: dict[str, Any] = {
        "finviz_auth_key_set": finviz_set,
        "deepseek_api_key_set": deepseek_set,
        "pipeline_available": is_available(),
        "test_symbol": test_symbol.upper(),
        "headline_count": 0,
        "sample_headline": None,
        "deepseek_probe_ok": False,
        "primary_model": deepseek_llm.PRIMARY_MODEL,
    }
    if not finviz_set:
        result["error"] = "FINVIZ_AUTH_KEY missing"
        return result

    headlines = _fetch_news_via_elite(test_symbol, max_items=2)
    result["headline_count"] = len(headlines)
    if headlines:
        result["sample_headline"] = headlines[0][:120]

    if not deepseek_set:
        result["error"] = "DEEPSEEK_API_KEY missing"
        return result
    if not headlines:
        result["error"] = "Finviz Elite returned no headlines — check auth key or symbol"
        return result

    sample = extract_catalyst(test_symbol)
    result["deepseek_probe_ok"] = bool(sample.get("tag"))
    if sample.get("tag"):
        result["sample_tag"] = sample["tag"]
    return result


def enrich_watchlist_with_catalysts(
    watchlist: list[dict[str, Any]],
    *,
    max_symbols: int = 30,
) -> dict[str, dict[str, Any]]:
    """Extract catalysts for symbols in the final watchlist (in list order)."""
    if not is_available():
        missing = []
        if not deepseek_llm.is_available():
            missing.append("DEEPSEEK_API_KEY")
        if not _FINVIZ_KEY:
            missing.append("FINVIZ_AUTH_KEY")
        logger.info("Catalyst enrichment skipped — missing: %s", ", ".join(missing))
        return {}

    candidates = [
        str(row["symbol"]).strip().upper()
        for row in watchlist
        if row.get("symbol")
    ][:max_symbols]

    if not candidates:
        logger.info("Catalyst enrichment skipped — watchlist has no symbols")
        return {}

    logger.info(
        "🔍 Extracting catalysts for %d final watchlist symbols via Finviz Elite + DeepSeek...",
        len(candidates),
    )
    results: dict[str, dict[str, Any]] = {}
    for i, sym in enumerate(candidates):
        catalyst = extract_catalyst(sym)
        if catalyst:
            results[sym] = catalyst
        if i < len(candidates) - 1:
            time.sleep(_CATALYST_SLEEP_SEC)

    logger.info(
        "Catalyst extraction complete: %d/%d symbols tagged",
        len(results), len(candidates),
    )
    return results
