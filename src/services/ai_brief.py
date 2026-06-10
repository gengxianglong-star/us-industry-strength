"""AI-powered market brief via DeepSeek API.

Usage
-----
1. Set ``DEEPSEEK_API_KEY`` in ``.env`` (or export it as an environment variable).
2. Call ``generate_ai_brief(...)`` with market data to get a natural-language briefing.
"""

from __future__ import annotations

from typing import Any

from src.logging_config import get_logger
from src.services import deepseek_llm

logger = get_logger(__name__)


def is_available() -> bool:
    """Return ``True`` if a DeepSeek API key has been configured."""
    return deepseek_llm.is_available()


async def generate_ai_brief(
    *,
    snapshot_date: str,
    industry_count: int,
    top_industries: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    breadth_latest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a daily market briefing using DeepSeek."""
    if not is_available():
        raise RuntimeError(
            "DeepSeek API 未配置。请在 .env 文件中设置 DEEPSEEK_API_KEY，"
            "或通过环境变量 export DEEPSEEK_API_KEY=你的密钥。"
        )

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
    if breadth_latest:
        up_q = breadth_latest.get("c5_num")
        down_q = breadth_latest.get("c6_num")
        up_m = breadth_latest.get("c7_num")
        down_m = breadth_latest.get("c8_num")
        t2108 = breadth_latest.get("c14_num")
        quarter = "BULL" if (up_q or 0) > (down_q or 0) else "BEAR"
        monthly = "BULLISH" if (up_m or 0) > (down_m or 0) else "BEARISH"
        breadth_line = (
            f"Market Breadth: Quarter={quarter} (Up25Q={up_q}, Down25Q={down_q}), "
            f"Monthly={monthly} (Up25M={up_m}, Down25M={down_m}), T2108={t2108}"
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
        brief_text, model = deepseek_llm.chat(
            prompt,
            max_tokens=1024,
            temperature=0.7,
            thinking="disabled",
        )
    except Exception as exc:
        logger.exception("DeepSeek API call failed")
        raise RuntimeError(f"DeepSeek API 调用失败: {exc}") from exc

    return {
        "brief": brief_text.strip() if brief_text else "（DeepSeek 未返回内容）",
        "model": model,
        "snapshot_date": snapshot_date,
    }
