"""AI-powered catalyst extraction for watchlist stocks via Google Gemini API.

Uses the same ``GEMINI_API_KEY`` from ``.env`` as ``ai_brief.py``.
Only fetches catalysts for stocks with RS >= 95 to stay fast and focused.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import yfinance as yf
from dotenv import load_dotenv
from google.genai import Client as GenAiClient
from google.genai import types as genai_types

from src.logging_config import get_logger

logger = get_logger(__name__)

load_dotenv()

_API_KEY: str | None = os.environ.get("GEMINI_API_KEY") or None

_client: GenAiClient | None = None


def _get_client() -> GenAiClient | None:
    global _client
    if _client is None and _API_KEY:
        _client = GenAiClient(api_key=_API_KEY)
    return _client


def is_available() -> bool:
    """Return ``True`` if a Gemini API key has been configured."""
    return _API_KEY is not None


def _fetch_news_headlines(symbol: str, max_items: int = 3) -> list[str]:
    """Fetch recent news headlines for a symbol via yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        news_items = ticker.news[:max_items]
        if not news_items:
            return []
        headlines: list[str] = []
        for item in news_items:
            title = str(item.get("title") or "").strip()
            if title:
                headlines.append(title)
        return headlines
    except Exception:
        logger.debug("yfinance news fetch failed for %s", symbol, exc_info=True)
        return []


def extract_catalyst(symbol: str) -> dict[str, Any]:
    """Fetch recent news and use Gemini to extract a Qullamaggie-style catalyst tag.

    Returns a dict with ``"tag"`` and ``"headlines"``, or an empty dict if
    no catalyst was found / the API key is missing.
    """
    client = _get_client()
    if client is None:
        return {}

    headlines = _fetch_news_headlines(symbol)
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
            return {}

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
        logger.info("Catalyst extraction skipped: GEMINI_API_KEY not configured")
        return {}

    candidates = [
        row["symbol"]
        for row in watchlist
        if float(row.get("rs_score", 0)) >= min_rs_score
    ][:max_symbols]

    if not candidates:
        return {}

    logger.info("Extracting catalysts for %d symbols (RS >= %.0f%%)...", len(candidates), min_rs_score * 100)
    results: dict[str, dict[str, Any]] = {}
    for i, sym in enumerate(candidates):
        catalyst = extract_catalyst(sym)
        if catalyst:
            results[sym] = catalyst
            logger.debug("  %s → %s", sym, catalyst["tag"])
        # Rate-limit: small delay between API calls
        if i < len(candidates) - 1:
            time.sleep(0.6)

    logger.info("Catalyst extraction complete: %d/%d symbols tagged", len(results), len(candidates))
    return results
