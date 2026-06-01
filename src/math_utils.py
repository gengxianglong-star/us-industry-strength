"""Shared math utilities for percentile, ranking, and weight normalization."""

from __future__ import annotations

from typing import Any


def percentile_rank(rank: int, total: int) -> float:
    """Convert a 1-based rank to a 0-1 percentile score.

    Rank 1 in a set of N → 1.0 (top), rank N → 0.0 (bottom).
    """
    if total <= 1:
        return 1.0
    return 1.0 - (rank - 1) / (total - 1)


def rank_dict_by_key(
    rows: list[dict[str, Any]],
    key: str,
    *,
    id_key: str = "symbol",
    reverse: bool = True,
) -> dict[str, int]:
    """Assign 1-based ranks to a list of dicts by a given key.

    Returns a mapping from id_key value → rank (1 = best).
    """
    ordered = sorted(rows, key=lambda r: r[key], reverse=reverse)
    return {row[id_key]: idx + 1 for idx, row in enumerate(ordered)}


def normalize_weights(
    weight_map: dict[str, float],
    *,
    total_min: float = 0.0,
) -> dict[str, float]:
    """Normalize a dict of weights so they sum to 1.0.

    If the total is <= total_min, returns equal weights.
    """
    total = sum(float(v) for v in weight_map.values())
    n = len(weight_map)
    if n == 0:
        return {}
    if total <= total_min:
        return {k: 1.0 / n for k in weight_map}
    return {k: float(v) / total for k, v in weight_map.items()}
