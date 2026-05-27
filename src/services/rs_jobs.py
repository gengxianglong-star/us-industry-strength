"""RS job orchestration service."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.jobs.claim import claim_background_job
from src.stock_rs import backfill_new_stock_rs_for_snapshot, compute_and_store_stock_rs
from src.storage import Storage


class JobCancelledError(RuntimeError):
    """Raised when a running job is cancelled by user request."""


class RsJobService:
    STALE_SECONDS = 30 * 60

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}
        self._cancel_flags: dict[str, bool] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _state_key(snapshot_date: str, job_kind: str) -> str:
        return f"{snapshot_date}:{job_kind}"

    @staticmethod
    def _job_timestamps(job: dict[str, Any]) -> tuple[float | None, float | None]:
        started_ts = None
        updated_ts = None
        try:
            if job.get("started_at"):
                started_ts = datetime.fromisoformat(str(job["started_at"])).timestamp()
            if job.get("updated_at"):
                updated_ts = datetime.fromisoformat(str(job["updated_at"])).timestamp()
        except ValueError:
            pass
        return started_ts, updated_ts

    def _state_from_db_job(self, job: dict[str, Any]) -> dict[str, Any]:
        started_ts, updated_ts = self._job_timestamps(job)
        return {
            "status": job.get("status", "idle"),
            "job_id": job.get("job_id"),
            "processed": int(job.get("processed") or 0),
            "total": int(job.get("total") or 0),
            "started_at": started_ts,
            "updated_at": updated_ts,
            "result": job.get("result") or {},
            "error": job.get("error"),
        }

    def _set_progress(self, snapshot_date: str, job_kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._state[self._state_key(snapshot_date, job_kind)] = payload

    def _get_progress(self, snapshot_date: str, job_kind: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._state.get(self._state_key(snapshot_date, job_kind)) or {})

    def _set_cancel_flag(self, snapshot_date: str, job_kind: str, value: bool) -> None:
        with self._lock:
            self._cancel_flags[self._state_key(snapshot_date, job_kind)] = value

    def _is_cancelled(self, snapshot_date: str, job_kind: str) -> bool:
        with self._lock:
            return bool(self._cancel_flags.get(self._state_key(snapshot_date, job_kind), False))

    def _active_job_response(
        self,
        *,
        snapshot_date: str,
        job_kind: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "running",
            "snapshot_date": snapshot_date,
            "job_kind": job_kind,
            "job_id": state.get("job_id"),
        }

    def _start_job(
        self,
        *,
        storage: Storage,
        snapshot_date: str,
        job_kind: str,
        run_fn: Any,
        async_mode: bool,
        max_runtime_seconds: int,
    ) -> dict[str, Any]:
        with self._lock:
            state = dict(self._state.get(self._state_key(snapshot_date, job_kind)) or {})
            if state.get("status") in {"running", "cancelling"}:
                updated = float(state.get("updated_at") or state.get("started_at") or 0)
                if updated and (time.time() - updated) <= self.STALE_SECONDS:
                    return self._active_job_response(
                        snapshot_date=snapshot_date,
                        job_kind=job_kind,
                        state=state,
                    )

            db_job = storage.get_latest_rs_job_run(snapshot_date, job_kind=job_kind)
            if db_job and str(db_job.get("status") or "") in {"running", "cancelling"}:
                db_state = self._state_from_db_job(db_job)
                updated = float(db_state.get("updated_at") or db_state.get("started_at") or 0)
                if updated and (time.time() - updated) <= self.STALE_SECONDS:
                    self._state[self._state_key(snapshot_date, job_kind)] = db_state
                    return self._active_job_response(
                        snapshot_date=snapshot_date,
                        job_kind=job_kind,
                        state=db_state,
                    )

            start_ts = time.time()
            job_id = f"{job_kind}-{snapshot_date}-{uuid4().hex[:10]}"
            claimed, blocking = claim_background_job(
                storage,
                scope=snapshot_date,
                kind=job_kind,
                job_id=job_id,
                stale_seconds=self.STALE_SECONDS,
            )
            if not claimed and blocking:
                blocked_state = self._state_from_db_job(blocking)
                self._state[self._state_key(snapshot_date, job_kind)] = blocked_state
                return self._active_job_response(
                    snapshot_date=snapshot_date,
                    job_kind=job_kind,
                    state=blocked_state,
                )

            self._state[self._state_key(snapshot_date, job_kind)] = {
                "status": "running",
                "job_id": job_id,
                "processed": 0,
                "total": 0,
                "started_at": start_ts,
                "updated_at": start_ts,
            }
            self._cancel_flags[self._state_key(snapshot_date, job_kind)] = False

        def _run_job() -> None:
            def _on_progress(processed: int, total: int) -> None:
                now_ts = time.time()
                if self._is_cancelled(snapshot_date, job_kind):
                    raise JobCancelledError(f"{job_kind} cancelled by user")
                if now_ts - start_ts > max_runtime_seconds:
                    raise TimeoutError(f"{job_kind} exceeded {max_runtime_seconds}s")
                self._set_progress(
                    snapshot_date,
                    job_kind,
                    {
                        "status": "running",
                        "job_id": job_id,
                        "processed": processed,
                        "total": total,
                        "started_at": start_ts,
                        "updated_at": now_ts,
                    },
                )
                storage.upsert_rs_job_run(
                    job_id,
                    snapshot_date,
                    "running",
                    job_kind=job_kind,
                    processed=processed,
                    total=total,
                )

            try:
                result = run_fn(_on_progress)
                end_ts = time.time()
                final_state = {
                    "status": "done",
                    "job_id": job_id,
                    "processed": int(result.get("attempted_count", result.get("fetched_symbols", 0)) or 0),
                    "total": int(result.get("attempted_count", result.get("fetched_symbols", 0)) or 0),
                    "started_at": start_ts,
                    "updated_at": end_ts,
                    "elapsed_seconds": round(end_ts - start_ts, 2),
                    "result": result,
                }
                self._set_progress(snapshot_date, job_kind, final_state)
                storage.upsert_rs_job_run(
                    job_id,
                    snapshot_date,
                    "done",
                    job_kind=job_kind,
                    processed=final_state["processed"],
                    total=final_state["total"],
                    result=result,
                    finished=True,
                )
            except Exception as exc:  # noqa: BLE001
                end_ts = time.time()
                previous = self._get_progress(snapshot_date, job_kind)
                status = "cancelled" if isinstance(exc, JobCancelledError) else "error"
                err_state = {
                    "status": status,
                    "job_id": job_id,
                    "processed": int(previous.get("processed") or 0),
                    "total": int(previous.get("total") or 0),
                    "started_at": start_ts,
                    "updated_at": end_ts,
                    "elapsed_seconds": round(end_ts - start_ts, 2),
                    "error": str(exc),
                }
                self._set_progress(snapshot_date, job_kind, err_state)
                storage.upsert_rs_job_run(
                    job_id,
                    snapshot_date,
                    status,
                    job_kind=job_kind,
                    processed=err_state["processed"],
                    total=err_state["total"],
                    error=str(exc),
                    finished=True,
                )
                if status == "cancelled":
                    storage.upsert_snapshot_run(
                        snapshot_date,
                        "running",
                        current_step=f"{job_kind}_cancelled",
                        details={"reason": "cancelled"},
                    )
                else:
                    storage.upsert_snapshot_run(
                        snapshot_date,
                        "failed",
                        current_step=f"{job_kind}_failed",
                        error=str(exc),
                    )
            finally:
                self._set_cancel_flag(snapshot_date, job_kind, False)

        if async_mode:
            threading.Thread(target=_run_job, daemon=True).start()
            return {"status": "started", "snapshot_date": snapshot_date, "job_kind": job_kind, "job_id": job_id}

        _run_job()
        final = self._get_progress(snapshot_date, job_kind)
        if final.get("status") in {"error", "cancelled"}:
            raise RuntimeError(final.get("error") or f"{job_kind} failed")
        return {"status": "ok", **(final.get("result") or {})}

    def start_compute_rs(
        self,
        *,
        storage: Storage,
        snapshot_date: str,
        scored: list[Any],
        config: dict[str, Any],
        async_mode: bool = True,
    ) -> dict[str, Any]:
        max_runtime = int(config.get("stock_rs", {}).get("max_job_runtime_seconds", 7200))

        def _run(progress_cb: Any) -> dict[str, Any]:
            result = compute_and_store_stock_rs(
                storage,
                snapshot_date,
                scored,
                config,
                progress_callback=progress_cb,
            )
            if int(result.get("new_stock_leaderboard_count", 0) or 0) <= 0:
                if int(result.get("insufficient_history_count", 0) or 0) > 0:
                    backfill = backfill_new_stock_rs_for_snapshot(
                        storage,
                        snapshot_date,
                        config,
                        progress_callback=progress_cb,
                    )
                    result = {**result, **backfill}
            storage.upsert_snapshot_run(
                snapshot_date,
                "running",
                current_step="stock_rs_async_done",
                details={
                    "rs_computed_count": int(result.get("computed_count", 0) or 0),
                },
            )
            return result

        return self._start_job(
            storage=storage,
            snapshot_date=snapshot_date,
            job_kind="main",
            run_fn=_run,
            async_mode=async_mode,
            max_runtime_seconds=max_runtime,
        )

    def start_compute_new_rs(
        self,
        *,
        storage: Storage,
        snapshot_date: str,
        config: dict[str, Any],
        async_mode: bool = True,
    ) -> dict[str, Any]:
        max_runtime = int(config.get("stock_rs", {}).get("new_stock_job_runtime_seconds", 3600))

        def _run(progress_cb: Any) -> dict[str, Any]:
            return backfill_new_stock_rs_for_snapshot(
                storage,
                snapshot_date,
                config,
                progress_callback=progress_cb,
            )

        return self._start_job(
            storage=storage,
            snapshot_date=snapshot_date,
            job_kind="new",
            run_fn=_run,
            async_mode=async_mode,
            max_runtime_seconds=max_runtime,
        )

    def get_progress(self, snapshot_date: str, *, storage: Storage, job_kind: str = "main") -> dict[str, Any]:
        state = self._get_progress(snapshot_date, job_kind)
        if not state:
            job = storage.get_latest_rs_job_run(snapshot_date, job_kind=job_kind)
            if job:
                state = self._state_from_db_job(job)
        if not state:
            return {"snapshot_date": snapshot_date, "status": "idle", "processed": 0, "total": 0}
        total = int(state.get("total") or 0)
        processed = int(state.get("processed") or 0)
        progress_ratio = (processed / total) if total > 0 else 0
        return {
            "snapshot_date": snapshot_date,
            "job_kind": job_kind,
            "status": state.get("status", "running"),
            "job_id": state.get("job_id"),
            "processed": processed,
            "total": total,
            "progress_ratio": round(progress_ratio, 4),
            "started_at": state.get("started_at"),
            "updated_at": state.get("updated_at"),
            "elapsed_seconds": state.get("elapsed_seconds"),
            "error": state.get("error"),
            "result": state.get("result"),
        }

    def request_cancel(self, snapshot_date: str, *, storage: Storage, job_kind: str = "main") -> dict[str, Any]:
        state = self._get_progress(snapshot_date, job_kind)
        if not state:
            job = storage.get_latest_rs_job_run(snapshot_date, job_kind=job_kind)
            if job and str(job.get("status") or "") == "running":
                state = self._state_from_db_job(job)
        if state.get("status") != "running":
            return {
                "snapshot_date": snapshot_date,
                "job_kind": job_kind,
                "status": "idle",
                "message": "no running job",
            }
        self._set_cancel_flag(snapshot_date, job_kind, True)
        now_ts = time.time()
        self._set_progress(
            snapshot_date,
            job_kind,
            {
                **state,
                "status": "cancelling",
                "updated_at": now_ts,
            },
        )
        storage.upsert_rs_job_run(
            str(state.get("job_id") or ""),
            snapshot_date,
            "cancelling",
            job_kind=job_kind,
            processed=int(state.get("processed") or 0),
            total=int(state.get("total") or 0),
        )
        return {
            "snapshot_date": snapshot_date,
            "job_kind": job_kind,
            "status": "cancelling",
            "job_id": state.get("job_id"),
        }
