"""Breadth sync job orchestration."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.breadth_data import sync_breadth_history
from src.config_loader import load_config
from src.jobs.claim import claim_background_job
from src.storage import Storage

BREADTH_JOB_SCOPE = "__breadth__"
BREADTH_JOB_KIND = "sync"


class BreadthSyncService:
    STALE_SECONDS = 15 * 60

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "status": "idle",
            "mode": "incremental",
            "processed": 0,
            "total": 0,
            "started_at": None,
            "updated_at": None,
        }
        self._lock = threading.Lock()

    def _update_state(self, **kwargs: Any) -> None:
        with self._lock:
            self._state.update(kwargs)

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def get_progress_state(self, storage: Storage) -> dict[str, Any]:
        state = self.get_state()
        mem_status = str(state.get("status") or "idle")
        if mem_status in {"running", "done", "error"}:
            return state

        db_job = storage.get_latest_rs_job_run(BREADTH_JOB_SCOPE, job_kind=BREADTH_JOB_KIND)
        if not db_job:
            return state

        db_status = str(db_job.get("status") or "")
        if db_status in {"running", "cancelling"}:
            return {
                "status": "running",
                "mode": state.get("mode") or "incremental",
                "processed": int(db_job.get("processed") or 0),
                "total": int(db_job.get("total") or 0),
                "started_at": db_job.get("started_at"),
                "updated_at": db_job.get("updated_at"),
                "message": "running (recovered from job store)",
                "job_id": db_job.get("job_id"),
            }
        if db_status == "error":
            return {
                "status": "error",
                "error": db_job.get("error") or "sync failed",
                "job_id": db_job.get("job_id"),
                "updated_at": db_job.get("updated_at"),
            }
        if db_status == "done":
            try:
                result = db_job.get("result") or {}
            except Exception:  # noqa: BLE001
                result = {}
            return {
                "status": "done",
                "mode": (result or {}).get("mode") or state.get("mode"),
                "result": result,
                "job_id": db_job.get("job_id"),
                "updated_at": db_job.get("updated_at"),
            }
        return state

    def start_sync(
        self,
        storage: Storage,
        *,
        full: bool = False,
        async_mode: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            if self._state.get("status") == "running":
                return {"status": "running", **dict(self._state)}

        job_id = f"breadth-{uuid4().hex[:10]}"
        claimed, blocking = claim_background_job(
            storage,
            scope=BREADTH_JOB_SCOPE,
            kind=BREADTH_JOB_KIND,
            job_id=job_id,
            stale_seconds=self.STALE_SECONDS,
        )
        if not claimed:
            blocked = dict(blocking or {})
            age_seconds = self.STALE_SECONDS + 1
            try:
                updated = datetime.fromisoformat(str(blocked.get("updated_at")))
                age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
            except (TypeError, ValueError):
                pass
            mem_idle = self.get_state().get("status") != "running"
            if mem_idle and age_seconds > 90 and blocked.get("job_id"):
                storage.upsert_rs_job_run(
                    str(blocked["job_id"]),
                    BREADTH_JOB_SCOPE,
                    "error",
                    job_kind=BREADTH_JOB_KIND,
                    error="orphan sync job recovered",
                    finished=True,
                )
                claimed, blocking = claim_background_job(
                    storage,
                    scope=BREADTH_JOB_SCOPE,
                    kind=BREADTH_JOB_KIND,
                    job_id=job_id,
                    stale_seconds=self.STALE_SECONDS,
                )
            if not claimed:
                blocked = dict(blocking or {})
                return {
                    **self.get_state(),
                    "status": "running",
                    "blocked": True,
                    "job_id": blocked.get("job_id"),
                    "message": "another sync is in progress",
                }

        started_at = time.time()
        mode = "full" if full else "incremental"
        self._update_state(
            status="running",
            mode=mode,
            processed=0,
            total=0,
            started_at=started_at,
            updated_at=started_at,
            message="starting",
            job_id=job_id,
            error=None,
            result=None,
            elapsed_seconds=None,
        )

        def _run() -> None:
            def _on_progress(processed: int, total: int, gid: str) -> None:
                self._update_state(
                    processed=processed,
                    total=total,
                    updated_at=time.time(),
                    message=f"processing gid={gid}",
                )
                storage.upsert_rs_job_run(
                    job_id,
                    BREADTH_JOB_SCOPE,
                    "running",
                    job_kind=BREADTH_JOB_KIND,
                    processed=processed,
                    total=total,
                )

            try:
                result = sync_breadth_history(
                    storage,
                    full=full,
                    progress_callback=_on_progress,
                    config=load_config(),
                )
                ended_at = time.time()
                storage.upsert_rs_job_run(
                    job_id,
                    BREADTH_JOB_SCOPE,
                    "done",
                    job_kind=BREADTH_JOB_KIND,
                    finished=True,
                    result=result,
                )
                self._update_state(
                    status="done",
                    result=result,
                    updated_at=ended_at,
                    elapsed_seconds=round(ended_at - started_at, 2),
                    message="done",
                    error=None,
                )
            except Exception as exc:  # noqa: BLE001
                ended_at = time.time()
                err_text = str(exc)
                storage.upsert_rs_job_run(
                    job_id,
                    BREADTH_JOB_SCOPE,
                    "error",
                    job_kind=BREADTH_JOB_KIND,
                    error=err_text,
                    finished=True,
                )
                self._update_state(
                    status="error",
                    error=err_text,
                    updated_at=ended_at,
                    elapsed_seconds=round(ended_at - started_at, 2),
                    message="error",
                )

        if async_mode:
            threading.Thread(target=_run, daemon=True).start()
            return {"status": "started", "mode": mode, "job_id": job_id}

        _run()
        state = self.get_state()
        if state.get("status") == "error":
            raise RuntimeError(state.get("error") or "breadth sync failed")
        return {"status": "ok", "full": full, **(state.get("result") or {})}
