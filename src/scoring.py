"""Rank industries and compute composite strength scores."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.config_loader import TIMEFRAMES
from src.math_utils import percentile_rank, rank_dict_by_key, weighted_momentum_composite
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


def top_strong_sort_key(
    score: float,
    rank_m: int,
    rank_q: int,
    industry_key: str = "",
) -> tuple[float, int, int, str]:
    """Shared Top-N tie-break: higher score, then better month/quarter ranks."""
    return (-float(score), int(rank_m), int(rank_q), str(industry_key))


def score_industries(rows: list[IndustryRow], config: dict[str, Any]) -> list[ScoredIndustry]:
    thresholds = config.get("thresholds", {})
    weights = config["_normalized_weights"]

    tier_a = float(thresholds.get("tier_a_score", 0.80))
    tier_b = float(thresholds.get("tier_b_score", 0.65))
    core_rank_max = int(thresholds.get("core_rank_max", 25))
    max_spread = int(thresholds.get("max_rank_spread", 60))
    accel_delta = int(thresholds.get("acceleration_rank_delta", 5))
    pullback_midterm_rank_max = int(thresholds.get("pullback_midterm_rank_max", 30))
    pullback_week_rank_min = int(thresholds.get("pullback_week_rank_min", 40))

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

        item.score = weighted_momentum_composite(
            {
                "perf_w": item.perf_w,
                "perf_m": item.perf_m,
                "perf_q": item.perf_q,
                "perf_h": item.perf_h,
                "perf_y": item.perf_y,
            },
            weights,
        )

        scored.append(item)

    score_ranks = rank_dict_by_key(
        [{"industry_key": item.key, "score": item.score} for item in scored],
        "score",
        id_key="industry_key",
    )
    for item in scored:
        strength = percentile_rank(score_ranks[item.key], total)
        if strength >= tier_a:
            item.tier = "A"
        elif strength >= tier_b:
            item.tier = "B"
        else:
            item.tier = "C"

        rank_values = [item.rank_w, item.rank_m, item.rank_q, item.rank_h, item.rank_y]
        spread = max(rank_values) - min(rank_values)
        core_ok = (
            item.rank_m <= core_rank_max
            and item.rank_q <= core_rank_max
            and item.rank_h <= core_rank_max
            and spread <= max_spread
        )
        if core_ok and item.tier == "A":
            item.tags.append("Core")

        # 以3个月排名为锚：月度优于3个月=加速；月度弱于3个月=回调
        # acceleration_rank_delta：周排名需比月排名至少好/差这么多名才打箭头标签。
        week_vs_month = item.rank_m - item.rank_w
        if item.rank_m < item.rank_q:
            if week_vs_month >= accel_delta:
                if item.rank_w < item.rank_m:
                    item.tags.append("Accel↑")
                elif item.rank_w > item.rank_m:
                    item.tags.append("Accel↓")
                else:
                    item.tags.append("Accel")
            elif week_vs_month <= -accel_delta and item.rank_w > item.rank_m:
                item.tags.append("Accel↓")
        elif item.rank_m > item.rank_q:
            if item.rank_w < item.rank_m:
                item.tags.append("Pullback↑")
            elif item.rank_w > item.rank_m:
                item.tags.append("Pullback↓")
            else:
                item.tags.append("Pullback")

        pullback_mid_ok = (
            item.rank_m <= pullback_midterm_rank_max
            and item.rank_q <= pullback_midterm_rank_max
            and item.rank_h <= pullback_midterm_rank_max
        )
        if pullback_mid_ok and item.rank_w >= pullback_week_rank_min and item.perf_w < 0:
            item.tags.append("Strong PB")

        if item.rank_m > 80 and item.rank_h > 60:
            item.tags.append("Weak")

    scored.sort(key=lambda x: top_strong_sort_key(x.score, x.rank_m, x.rank_q, x.key))
    return scored


def filter_core_strong(
    scored: list[ScoredIndustry], config: dict[str, Any]
) -> list[ScoredIndustry]:
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    core = [s for s in scored if not s.excluded and "Core" in s.tags]
    core.sort(key=lambda x: top_strong_sort_key(x.score, x.rank_m, x.rank_q, x.key))
    return core[:top_n]


def filter_top_strong(
    scored: list[ScoredIndustry],
    config: dict[str, Any],
    *,
    stock_picks: dict[str, Any] | None = None,
) -> list[ScoredIndustry]:
    """Top N industries by score; skip empty screener hits and backfill from lower ranks."""
    top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
    active = [s for s in scored if not s.excluded]
    active.sort(key=lambda x: top_strong_sort_key(x.score, x.rank_m, x.rank_q, x.key))
    if stock_picks is None:
        return active[:top_n]
    selected: list[ScoredIndustry] = []
    for item in active:
        if len(selected) >= top_n:
            break
        tickers = (stock_picks.get(item.key) or {}).get("tickers") or []
        if tickers:
            selected.append(item)
    return selected
