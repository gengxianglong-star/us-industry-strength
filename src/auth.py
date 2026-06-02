"""API key authentication for write-protected endpoints.

Uses a FastAPI dependency that checks the X-API-Key header.
Read endpoints (GET) skip auth; write endpoints (POST/PUT/DELETE) require it.

Usage in server.py::

    from src.auth import require_api_key

    @app.post("/api/daily/run", dependencies=[Depends(require_api_key)])
    def daily_run(...): ...
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, Request

_LOCAL_ADDRESSES = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_localhost(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in _LOCAL_ADDRESSES


def _api_settings(config: dict[str, Any]) -> tuple[bool, str]:
    api_cfg = config.get("api") or {}
    enabled = bool(api_cfg.get("enabled", False))
    key = str(api_cfg.get("key") or "")
    return enabled, key


def require_api_key(request: Request) -> None:
    """FastAPI dependency: reject requests without a valid X-API-Key header.

    Skips check when:
    - ``api.enabled`` is ``false`` in config.yaml (default — backward compatible)
    - Request originates from localhost
    """
    config: dict[str, Any] = getattr(request.app.state, "config", {})
    enabled, expected_key = _api_settings(config)

    if not enabled:
        return

    if not expected_key:
        return

    if _is_localhost(request):
        return

    provided = (request.headers.get("X-API-Key") or "").strip()
    if not secrets.compare_digest(provided, expected_key):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing or invalid X-API-Key header",
                "hint": "Add header X-API-Key: <your-api-key> or call from localhost",
                "retryable": False,
            },
        )
