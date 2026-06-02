"""Centralized structured logging for the US Industry Strength project.

Replaces ad-hoc print() calls with configurable log levels, file rotation,
and consistent formatting. Each module gets its own logger via get_logger().
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LOGGERS: dict[str, logging.Logger] = {}
_LOGGING_INITIALIZED = False


def _ensure_initialized(config: dict[str, Any] | None = None) -> None:
    """Lazy-init so logging works even before config is loaded."""
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return

    root = logging.getLogger()
    root.handlers.clear()

    handler: logging.Handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    root.addHandler(handler)

    level = logging.INFO
    log_file: str = ""

    if config:
        cfg = config.get("logging") or {}
        raw_level = str(cfg.get("level", "INFO")).upper()
        level = getattr(logging, raw_level, logging.INFO)
        log_file = str(cfg.get("file") or "")

    root.setLevel(level)

    if log_file:
        file_path = Path(log_file)
        if not file_path.is_absolute():
            from src.config_loader import ROOT

            file_path = ROOT / log_file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(file_path), encoding="utf-8")
        fh.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
        root.addHandler(fh)

    _LOGGING_INITIALIZED = True


def setup_logging(config: dict[str, Any]) -> None:
    """Initialize logging from config (call once after config loads)."""
    _ensure_initialized(config)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger.

    Usage::

        from src.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Fetching industries...")
    """
    if name not in _LOGGERS:
        _ensure_initialized()
        _LOGGERS[name] = logging.getLogger(name)
    return _LOGGERS[name]
