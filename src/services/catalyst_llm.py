"""AI-powered catalyst extraction for watchlist stocks via Finviz Elite + Gemini.

Uses ``FINVIZ_AUTH_KEY`` to fetch news from the Finviz Elite quote page
(direct, ad-free, no IP blocking), then extracts a Qullamaggie-style
bullish catalyst tag via Gemini 2.0 Flash.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google.genai import Client as GenAiClient
from google.genai import types as genai_types

from src.logging_config import get_logger

logger = get_logger(__name__)

load_dotenv()

_GEMINI_KEY: str | None = os.environ.get("GEMINI_API_KEY") or None
_FINVIZ_KEY: str | None = (
    os.environ.get("FINVIZ_AUTH_KEY") or os.environ.get("FINVIZ_ELITE_AUTH") or None
)

_client: GenAiClient | None = None

_ELITE_QUOTE_URL = "https://elite.finviz.com/quote.ashx"
_ELITE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _get_client() -> GenAiClient | None:
    global _client
    if _client is None and _GEMINI_KEY:
        _client = GenAiClient(api_key=_GEMINI_KEY)
    return _client


def is_available() -> bool:
    """Return ``True`` if both Gemini API key and Finviz Elite key are set."""
    return _GEMINI_KEY is not None and _FINVIZ_KEY is not None


def _fetch_news_via_elite(symbol: str, max_items: int = 4) -> list[str]:
    """Fetch recent news headlines from the Finviz Elite quote page.

    Uses the authenticated Elite URL (``?auth=...``) to bypass ad pages
    and avoid IP blocking.  Parses the ``#news-table`` table rows.
    """
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
    """Fetch recent news via Finviz Elite and use Gemini to extract a
    Qullamaggie-style catalyst tag.

    Returns a dict with ``"tag"`` and ``"headlines"``, or an empty dict if
    no catalyst was found, keys are missing, or the call fails.
    """
    client = _get_client()
    if client is None:
        logger.debug("Gemini client not available — skipping %s", symbol)
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
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                genai_types.Content(
                    role="user", parts=[genai_types.Part(text=prompt)]
                )
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0.3, max_output_tokens=32
            ),
        )
        tag = (response.text or "").strip().upper()

        if tag == "NONE" or len(tag) > 25 or not tag:
            logger.info("🤖 %s — AI tagged as noise (NONE)", symbol)
            return {}

        logger.info("✨ %s — catalyst: 【%s】", symbol, tag)
        return {
            "tag": tag,
            "headlines": headlines[:2],
        }

    except Exception:
        logger.warning("Gemini catalyst extraction failed for %s", symbol, exc_info=True)
        return {}


def enrich_watchlist_with_catalysts(
    watchlist: list[dict[str, Any]],
    *,
    min_rs_score: float = 0.80,
    max_symbols: int = 30,
) -> dict[str, dict[str, Any]]:
    """Extract catalysts for top RS stocks in the watchlist.

    Only processes stocks with RS >= *min_rs_score*, up to *max_symbols*,
    to keep API usage low and speed fast.

    Returns a mapping of ``symbol -> catalyst_dict`` (tag + headlines).
    """
    if not is_available():
        missing = []
        if not _GEMINI_KEY:
            missing.append("GEMINI_API_KEY")
        if not _FINVIZ_KEY:
            missing.append("FINVIZ_AUTH_KEY")
        logger.info("Catalyst enrichment skipped — missing: %s", ", ".join(missing))
        return {}

    candidates = [
        row["symbol"]
        for row in watchlist
        if float(row.get("rs_score", 0)) >= min_rs_score
    ][:max_symbols]

    if not candidates:
        logger.info("No watchlist stocks with RS >= %.0f — skipping catalyst enrichment", min_rs_score * 100)
        return {}

    logger.info(
        "🔍 Extracting catalysts for %d symbols (RS >= %.0f%%) via Finviz Elite + Gemini...",
        len(candidates), min_rs_score * 100,
    )
    results: dict[str, dict[str, Any]] = {}
    for i, sym in enumerate(candidates):
        catalyst = extract_catalyst(sym)
        if catalyst:
            results[sym] = catalyst
        if i < len(candidates) - 1:
            time.sleep(0.6)  # rate-limit between symbols

    logger.info(
        "Catalyst extraction complete: %d/%d symbols tagged",
        len(results), len(candidates),
    )
    return results
