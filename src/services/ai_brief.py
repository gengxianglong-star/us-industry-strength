"""AI-powered market brief via Google Gemini API.

Usage
-----
1. Set ``GEMINI_API_KEY`` in ``.env`` (or export it as an environment variable).
2. Call ``generate_brief(...)`` with market data to get a natural‑language briefing.

The Gemini client is initialised once and reused across requests.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from google.genai import Client as GenAiClient
from google.genai import types as genai_types

from src.logging_config import get_logger

logger = get_logger(__name__)

# ── load .env so we can read GEMINI_API_KEY ──────────────────────────
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


async def generate_ai_brief(
    *,
    snapshot_date: str,
    industry_count: int,
    top_industries: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    breadth_status: dict[str, Any] | None = None,
    cockpit_modules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a daily market briefing using the Gemini API.

    Parameters
    ----------
    snapshot_date:
        The trading date the data corresponds to.
    industry_count:
        Total number of industries scored.
    top_industries:
        Top N scored industries with their name, score, and rank info.
    watchlist:
        Cross‑watchlist stocks with symbol and RS score.
    breadth_status:
        Optional market‑breadth status (cockpit lights).
    cockpit_modules:
        Optional detailed cockpit module states.

    Returns
    -------
    A dict with keys ``"brief"`` (the markdown text), and ``"model"``.
    Raises ``RuntimeError`` if the API key is missing or the call fails.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError(
            "Gemini API 未配置。请在 .env 文件中设置 GEMINI_API_KEY，"
            "或通过环境变量 export GEMINI_API_KEY=你的密钥。"
        )

    # ── build the prompt ──────────────────────────────────────────────
    top_industry_lines = "\n".join(
        f"- {ind.get('key', '?')}  score={ind.get('score', 0):.3f}  "
        f"rank_m={ind.get('rank_m', '?')}  rank_q={ind.get('rank_q', '?')}"
        for ind in top_industries[:5]
    )

    watchlist_lines = "\n".join(
        f"- {row.get('symbol', '?')}  RS={row.get('rs_score', 0):.3f}"
        for row in watchlist[:10]
    )

    breadth_line = ""
    if cockpit_modules:
        q = cockpit_modules.get("quarter_trend", {})
        m = cockpit_modules.get("monthly_trend", {})
        t = cockpit_modules.get("extreme_alert", {})
        breadth_line = (
            f"Market Cockpit: Quarter={q.get('state', '?')}, "
            f"Monthly={m.get('state', '?')}, T2108={t.get('value', '?')} "
            f"({t.get('state', '?')})"
        )

    prompt = f"""你是一位专业的美股市场宽度分析师。请根据以下数据生成一份简洁的中文每日市场简报（markdown 格式，不超过 300 字）。

📅 快照日期：{snapshot_date}
📊 行业覆盖：{industry_count} 个行业

🏆 Top 强势行业（前 5）：
{top_industry_lines}

📋 观察名单中的强势个股（前 10）：
{watchlist_lines}

{'+ ' + breadth_line if breadth_line else ''}

请包含以下要素：
1. 大盘环境判断（Look-through）
2. 强势行业分析（Top Sectors）
3. 操作建议（Actionable Insights）
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
            config=genai_types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1024,
            ),
        )
    except Exception as exc:
        logger.exception("Gemini API call failed")
        raise RuntimeError(f"Gemini API 调用失败: {exc}") from exc

    brief_text = response.text.strip() if response.text else "（Gemini 未返回内容）"

    return {
        "brief": brief_text,
        "model": "gemini-2.0-flash",
        "snapshot_date": snapshot_date,
    }
