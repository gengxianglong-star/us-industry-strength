"""Rank industries and compute composite strength scores."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.config_loader import TIMEFRAMES
from src.finviz_scraper import IndustryRow

PERF_ATTR = {
    "week": "perf_w",
    "month": "perf_m",
    "quarter": "perf_q",
    "half": "perf_h",
    "year": "perf_y",
}


@dataclass
class ScoredIndustry:
    key: str
    name: str
    stocks: int
    perf_w: float
    perf_m: float
    perf_q: float
    perf_h: float
    perf_y: float
    rank_w: int
    rank_m: int
    rank_q: int
    rank_h: int
    rank_y: int
    score: float
    tier: str
    tags: list[str] = field(default_factory=list)
    excluded: bool = False
    exclude_reason: str | None = None
    finviz_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rank_by_performance(rows: list[IndustryRow], timeframe: str) -> dict[str, int]:
    attr = PERF_ATTR[timeframe]
    ordered = sorted(rows, key=lambda r: getattr(r, attr), reverse=True)
    return {row.key: idx + 1 for idx, row in enumerate(ordered)}


def _percentile(rank: int, total: int) -> float:
    if total <= 1:
        return 1.0
    return 1.0 - (rank - 1) / (total - 1)


def score_industries(rows: list[IndustryRow], config: dict[str, Any]) -> list[ScoredIndustry]:
    thresholds = config.get("thresholds", {})
    weights = config["_normalized_weights"]

    tier_a = float(thresholds.get("tier_a_score", 0.80))
    tier_b = float(thresholds.get("tier_b_score", 0.65))
    core_rank_max = int(thresholds.get("core_rank_max", 25))
    max_spread = int(thresholds.get("max_rank_spread", 60))

    ranks = {tf: _rank_by_performance(rows, tf) for tf in TIMEFRAMES}
    total = len(rows)
    scored: list[ScoredIndustry] = []

    for row in rows:
        item = ScoredIndustry(
            key=row.key,
            name=row.name,
            stocks=row.stocks,
            perf_w=row.perf_w,
            perf_m=row.perf_m,
            perf_q=row.perf_q,
            perf_h=row.perf_h,
            perf_y=row.perf_y,
            rank_w=ranks["week"][row.key],
            rank_m=ranks["month"][row.key],
            rank_q=ranks["quarter"][row.key],
            rank_h=ranks["half"][row.key],
            rank_y=ranks["year"][row.key],
            score=0.0,
            tier="C",
            finviz_url=row.finviz_url,
        )

        item.score = sum(
            weights[tf] * _percentile(ranks[tf][row.key], total) for tf in TIMEFRAMES
        )

        rank_values = [item.rank_w, item.rank_m, item.rank_q, item.rank_h, item.rank_y]
        spread = max(rank_values) - min(rank_values)

        if item.score >= tier_a:
            item.tier = "A"
        elif item.score >= tier_b:
            item.tier = "B"
        else:
            item.tier = "C"

        core_ok = (
            item.rank_m <= core_rank_max
            and item.rank_q <= core_rank_max
            and item.rank_h <= core_rank_max
            and spread <= max_spread
        )
        if core_ok and item.tier == "A":
            item.tags.append("核心强势")

        # 以3个月排名为锚：月度优于3个月=加速；月度弱于3个月=回调
        # 箭头由周度 vs 月度决定：周优于月=↑，周弱于月=↓。
        if item.rank_m < item.rank_q:
            if item.rank_w < item.rank_m:
                item.tags.append("加速↑")
            elif item.rank_w > item.rank_m:
                item.tags.append("加速↓")
            else:
                item.tags.append("加速")
        elif item.rank_m > item.rank_q:
            if item.rank_w < item.rank_m:
                item.tags.append("回调↑")
            elif item.rank_w > item.rank_m:
                item.tags.append("回调↓")
            else:
                item.tags.append("回调")

        if item.rank_m > 80 and item.rank_h > 60:
            item.tags.append("走弱")

        scored.append(item)

    scored.sort(key=lambda x: (-x.score, x.rank_m, x.rank_q))
    return scored


def filter_core_strong(
    scored: list[ScoredIndustry], config: dict[str, Any]
) -> list[ScoredIndustry]:
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    core = [s for s in scored if not s.excluded and "核心强势" in s.tags]
    return core[:top_n]


def filter_top_strong(
    scored: list[ScoredIndustry], config: dict[str, Any]
) -> list[ScoredIndustry]:
    """Top N industries by composite score (main dashboard list)."""
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    active = [s for s in scored if not s.excluded]
    return active[:top_n]
