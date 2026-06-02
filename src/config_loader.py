"""Load, validate, and persist config.yaml."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"

TIMEFRAMES = ("week", "month", "quarter", "half", "year")
PERF_FIELDS = ("perf_w", "perf_m", "perf_q", "perf_h", "perf_y")
RANK_FIELDS = ("rank_w", "rank_m", "rank_q", "rank_h", "rank_y")

EDITABLE_KEYS = ("weights", "thresholds", "stock_filters", "stock_rs")
NESTED_EDITABLE_KEYS = frozenset({"stock_filters", "stock_rs"})


def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if value is None:
            continue
        merged[key] = value
    return merged


def merge_editable_config(
    existing: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Merge editable config; nested sections like stock_rs patch in-place."""
    merged = deepcopy(existing)
    for key in EDITABLE_KEYS:
        if key not in payload:
            continue
        incoming = payload[key]
        if key in NESTED_EDITABLE_KEYS and isinstance(incoming, dict):
            current = merged.get(key)
            if isinstance(current, dict):
                merged[key] = _deep_merge_dict(current, incoming)
            else:
                merged[key] = deepcopy(incoming)
        else:
            merged[key] = deepcopy(incoming)
    return merged


def _normalize_weights(config: dict[str, Any]) -> None:
    weights = config.get("weights", {})
    total = sum(float(weights.get(tf, 0)) for tf in TIMEFRAMES)
    if total <= 0:
        raise ValueError("weights 总和必须大于 0")
    config["_normalized_weights"] = {
        tf: float(weights.get(tf, 0)) / total for tf in TIMEFRAMES
    }


def _validate_config(config: dict[str, Any]) -> list[str]:
    """Validate config at load time; returns a list of warnings (non-fatal)."""
    warnings: list[str] = []

    rs_cfg = config.get("stock_rs") or {}
    adaptive = rs_cfg.get("adaptive_fetch") or {}
    if adaptive.get("enabled", True):
        max_passes = int(adaptive.get("max_passes", 5))
        worker_sched = list(adaptive.get("worker_schedule") or [10, 6, 3, 1])
        batch_sched = list(adaptive.get("batch_size_schedule") or [40, 20, 10, 5])

        # Adaptive fetch uses schedule[idx] where idx = min(pass_num - 1, len(sched) - 1).
        # With final_pass_single_symbol, the last tier uses single-symbol mode, so
        # worker_sched and batch_sched need at least max_passes - 1 entries for safe
        # batch-mode tiers plus the final single-symbol tier.
        if adaptive.get("final_pass_single_symbol", True):
            min_workers = max_passes - 1  # all but last are batch tiers
            min_batches = max_passes - 1
        else:
            min_workers = max_passes
            min_batches = max_passes

        if len(worker_sched) < min_workers:
            warnings.append(
                f"stock_rs.adaptive_fetch.worker_schedule has {len(worker_sched)} "
                f"entries but needs at least {min_workers} for max_passes={max_passes}"
            )
        if len(batch_sched) < min_batches:
            warnings.append(
                f"stock_rs.adaptive_fetch.batch_size_schedule has {len(batch_sched)} "
                f"entries but needs at least {min_batches} for max_passes={max_passes}"
            )

    return warnings


def load_config(path: Path | None = None, *, init_logging: bool = True) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    _normalize_weights(config)

    if init_logging:
        from src.logging_config import setup_logging

        setup_logging(config)

    warnings = _validate_config(config)
    if warnings:
        from src.logging_config import get_logger

        logger = get_logger(__name__)
        for w in warnings:
            logger.warning("config validation: %s", w)

    return config


def get_editable_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "weights": deepcopy(config.get("weights", {})),
        "thresholds": deepcopy(config.get("thresholds", {})),
        "stock_filters": deepcopy(config.get("stock_filters", {})),
        "stock_rs": deepcopy(config.get("stock_rs", {})),
    }


def save_editable_config(
    payload: dict[str, Any],
    path: Path | None = None,
    *,
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge editable fields into config.yaml and return reloaded config."""
    config_path = path or DEFAULT_CONFIG_PATH

    with config_path.open(encoding="utf-8") as f:
        existing = yaml.safe_load(f) or {}

    current_editable = get_editable_config(base_config or existing)
    merged_editable = merge_editable_config(current_editable, payload)
    for key in EDITABLE_KEYS:
        existing[key] = merged_editable[key]

    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(
            existing,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    return load_config(config_path)


def db_path(config: dict[str, Any]) -> Path:
    rel = config.get("database", {}).get("path", "data/industry_strength.db")
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    return path
