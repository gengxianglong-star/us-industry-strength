"""Shared DB-backed job slot claiming."""

from __future__ import annotations

from typing import Any

from src.storage import Storage


def claim_background_job(
    storage: Storage,
    *,
    scope: str,
    kind: str,
    job_id: str,
    stale_seconds: int,
) -> tuple[bool, dict[str, Any] | None]:
    return storage.claim_rs_job_run(
        job_id,
        scope,
        kind,
        stale_seconds=stale_seconds,
    )
