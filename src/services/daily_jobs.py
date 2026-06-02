"""Daily orchestration service: single pipeline entry, status, and dashboard."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.jobs.claim import claim_background_job
from src.logging_config import get_logger
from src.pipeline.daily import DailyPipelineOptions, run_daily_pipeline

logger = get_logger(__name__)
from src.services.daily_validation import (
    build_step_validations,
    build_validation_from_storage,
    _stale_days,
)
from src.services.health import check_db, check_proxy
from src.services.snapshots import top_strong_from_rows
from src.storage import Storage, latest_trading_date

PIPELINE_STEP_LABELS: list[tuple[str, str]] = [
    ("industry_fetch", "Industries"),
    ("stock_picks", "Top picks"),
    ("stock_rs", "Market RS"),
    ("breadth_sync", "Breadth"),
    ("done", "Done"),
]

STEP_INDEX: dict[str, int] = {
    "starting": 0,
    "pipeline": 0,
    "industry_fetch": 0,
    "stock_picks": 1,
    "stock_rs": 2,
    "stock_rs_async_done": 2,
    "awaiting_rs": 2,
    "breadth_sync": 3,
    "done": 4,
    "validation_failed": 4,
    "failed": 4,
}


def snapshots_needing_finalize_after_rs(storage: Storage) -> list[str]:
    """Snapshot dates where RS finished but the daily run was never closed out."""
    with storage._connect() as conn:
        rows = conn.execute(
            """
            SELECT sr.snapshot_date
            FROM snapshot_runs sr
            WHERE sr.current_step IN ('awaiting_rs', 'stock_rs_async_done')
              AND sr.status IN ('running', 'failed')
              AND EXISTS (
                SELECT 1 FROM snapshots s WHERE s.snapshot_date = sr.snapshot_date
              )
              AND EXISTS (
                SELECT 1 FROM rs_job_runs r
                WHERE r.snapshot_date = sr.snapshot_date
                  AND r.job_kind = 'main'
                  AND r.status = 'done'
              )
            ORDER BY sr.snapshot_date
            """
        ).fetchall()
    return [str(row["snapshot_date"]) for row in rows]


def finalize_snapshot_run(
    storage: Storage,
    config: dict[str, Any],
    snapshot_date: str,
    *,
    rs_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close out a daily run after RS finishes (or when rebuilding validation from DB)."""
    validation = build_validation_from_storage(storage, config=config, snapshot_date=snapshot_date)
    overall = str(validation.get("overall") or "degraded")
    run = storage.get_snapshot_run(snapshot_date) or {}
    details = dict(run.get("details") or {})
    details["validation"] = validation
    details["overall"] = overall
    if rs_result:
        details["rs_computed_count"] = int(rs_result.get("computed_count") or 0)
    status = "failed" if overall == "failed" else "completed"
    storage.upsert_snapshot_run(
        snapshot_date,
        status,
        current_step="done",
        details=details,
        finished=True,
        error=str(validation.get("headline")) if status == "failed" else None,
    )
    return validation


def daily_options_from_config(config: dict[str, Any]) -> DailyPipelineOptions:
    raw = (config.get("automation") or {}).get("daily") or {}
    return DailyPipelineOptions(
        skip_stocks=bool(raw.get("skip_stocks", False)),
        skip_rs=bool(raw.get("skip_rs", False)),
        skip_breadth=bool(raw.get("skip_breadth", True)),
        full_breadth=bool(raw.get("full_breadth", False)),
        force_full_rs=bool(raw.get("force_full_rs", False)),
        rs_async=bool(raw.get("rs_async", True)),
        verbose=bool(raw.get("verbose", True)),
    )


def pipeline_progress(current_step: str | None) -> dict[str, Any]:
    key = str(current_step or "starting")
    index = STEP_INDEX.get(key, 0)
    total = len(PIPELINE_STEP_LABELS)
    ratio = min(1.0, max(0.05, (index + 1) / total)) if key != "done" else 1.0
    label = next((lbl for step, lbl in PIPELINE_STEP_LABELS if step == key), key)
    return {
        "current_step": key,
        "current_label": label,
        "step_index": index,
        "step_total": total,
        "ratio": round(ratio, 4),
        "steps": [{"key": k, "label": v} for k, v in PIPELINE_STEP_LABELS],
    }


class DailyJobService:
    STALE_SECONDS = 30 * 60

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _state_key(snapshot_date: str) -> str:
        return snapshot_date

    def _get_state(self, snapshot_date: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._state.get(self._state_key(snapshot_date)) or {})

    def _set_state(self, snapshot_date: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._state[self._state_key(snapshot_date)] = payload

    def resolve_trade_date(self, snapshot_date: str | None = None) -> str:
        return snapshot_date or latest_trading_date()

    def resolve_display_date(
        self,
        storage: Storage,
        snapshot_date: str | None = None,
    ) -> str:
        if snapshot_date:
            return snapshot_date
        latest = storage.get_latest_date()
        return latest or latest_trading_date()

    def run_sync(
        self,
        storage: Storage,
        config: dict[str, Any],
        snapshot_date: str,
        *,
        options: DailyPipelineOptions | None = None,
    ) -> dict[str, Any]:
        opts = options or daily_options_from_config(config)
        result = run_daily_pipeline(storage, config, snapshot_date, opts)
        validation = build_step_validations(result, config=config, storage=storage, snapshot_date=snapshot_date)
        result["validation"] = validation
        overall = validation["overall"]
        if overall == "failed":
            storage.upsert_snapshot_run(
                snapshot_date,
                "failed",
                current_step="validation_failed",
                error=validation.get("headline"),
                details={"validation": validation, **self._summary_details(result)},
                finished=True,
            )
            raise RuntimeError(str(validation.get("headline") or "Daily validation failed"))
        rs_async = bool((result.get("rs") or {}).get("async_started"))
        if rs_async:
            storage.upsert_snapshot_run(
                snapshot_date,
                "running",
                current_step="awaiting_rs",
                details={
                    "validation": validation,
                    "overall": overall,
                    **self._summary_details(result),
                },
                finished=False,
            )
            return result
        storage.upsert_snapshot_run(
            snapshot_date,
            "completed",
            current_step="done",
            details={
                "validation": validation,
                "overall": overall,
                **self._summary_details(result),
            },
            finished=True,
        )
        return result

    def start_run(
        self,
        storage: Storage,
        config: dict[str, Any],
        snapshot_date: str | None = None,
        *,
        force: bool = False,
        async_mode: bool = True,
    ) -> dict[str, Any]:
        date_key = self.resolve_trade_date(snapshot_date)
        if not force:
            status = self.get_status(storage, config, date_key)
            if status.get("status") == "running":
                return {
                    "status": "running",
                    "snapshot_date": date_key,
                    "job_id": status.get("job_id"),
                    "message": "daily job already running",
                }
            if status.get("daily_status") in {"ready", "degraded"}:
                return {
                    "status": "skipped",
                    "snapshot_date": date_key,
                    "daily_status": status.get("daily_status"),
                    "message": "already up to date",
                }

        job_id = f"daily-{date_key}-{uuid4().hex[:10]}"
        with self._lock:
            state = self._get_state(date_key)
            if not force and state.get("status") == "running":
                updated = float(state.get("updated_at") or state.get("started_at") or 0)
                if updated and (time.time() - updated) <= self.STALE_SECONDS:
                    return {
                        "status": "running",
                        "snapshot_date": date_key,
                        "job_id": state.get("job_id"),
                    }

        claimed, blocking = claim_background_job(
            storage,
            scope=date_key,
            kind="daily",
            job_id=job_id,
            stale_seconds=self.STALE_SECONDS,
        )
        if not claimed and blocking:
            return {
                "status": "running",
                "snapshot_date": date_key,
                "job_id": blocking.get("job_id"),
                "message": "claimed by another worker",
            }

        start_ts = time.time()
        with self._lock:
            self._set_state(
                date_key,
                {
                    "status": "running",
                    "job_id": job_id,
                    "current_step": "starting",
                    "started_at": start_ts,
                    "updated_at": start_ts,
                },
            )

        def _run() -> None:
            try:
                self._set_state(
                    date_key,
                    {
                        **self._get_state(date_key),
                        "current_step": "pipeline",
                        "updated_at": time.time(),
                    },
                )
                self.run_sync(
                    storage,
                    config,
                    date_key,
                    options=daily_options_from_config(config),
                )
                end_ts = time.time()
                self._set_state(
                    date_key,
                    {
                        "status": "done",
                        "job_id": job_id,
                        "current_step": "done",
                        "started_at": start_ts,
                        "updated_at": end_ts,
                        "elapsed_seconds": round(end_ts - start_ts, 2),
                    },
                )
                storage.upsert_rs_job_run(
                    job_id,
                    date_key,
                    "done",
                    job_kind="daily",
                    finished=True,
                    result={"snapshot_date": date_key},
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("daily job failed for snapshot_date=%s", date_key)
                end_ts = time.time()
                self._set_state(
                    date_key,
                    {
                        "status": "error",
                        "job_id": job_id,
                        "current_step": "failed",
                        "error": str(exc),
                        "started_at": start_ts,
                        "updated_at": end_ts,
                        "elapsed_seconds": round(end_ts - start_ts, 2),
                    },
                )
                storage.upsert_rs_job_run(
                    job_id,
                    date_key,
                    "error",
                    job_kind="daily",
                    error=str(exc),
                    finished=True,
                )

        if async_mode:
            threading.Thread(target=_run, daemon=True).start()
            return {"status": "started", "snapshot_date": date_key, "job_id": job_id}

        _run()
        final = self._get_state(date_key)
        if final.get("status") == "error":
            raise RuntimeError(str(final.get("error") or "daily failed"))
        return {"status": "ok", "snapshot_date": date_key, "job_id": job_id}

    def get_status(
        self,
        storage: Storage,
        config: dict[str, Any],
        snapshot_date: str | None = None,
    ) -> dict[str, Any]:
        date_key = self.resolve_trade_date(snapshot_date)
        memory = self._get_state(date_key)
        if memory.get("status") == "running":
            updated = float(memory.get("updated_at") or memory.get("started_at") or 0)
            if updated and (time.time() - updated) <= self.STALE_SECONDS:
                return self._status_payload(date_key, memory, storage, config)

        run = storage.get_snapshot_run(date_key)
        if run and str(run.get("status") or "") == "running":
            updated_at = run.get("updated_at")
            age_ok = True
            if updated_at:
                try:
                    updated = datetime.fromisoformat(str(updated_at))
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=timezone.utc)
                    age_ok = (datetime.now(timezone.utc) - updated).total_seconds() <= self.STALE_SECONDS
                except ValueError:
                    age_ok = False
            if age_ok:
                step = run.get("current_step")
                return {
                    "snapshot_date": date_key,
                    "trade_date": date_key,
                    "status": "running",
                    "current_step": step,
                    "progress": pipeline_progress(step),
                    "started_at": run.get("started_at"),
                    "updated_at": run.get("updated_at"),
                    "daily_status": "running",
                    "cockpit_light": "blue",
                    "headline": f"Updating {date_key}…",
                    "pipeline": {"steps": (run.get("details") or {}).get("validation", {}).get("steps", {})},
                }

        db_job = storage.get_latest_rs_job_run(date_key, job_kind="daily")
        if db_job and str(db_job.get("status") or "") == "running":
            return {
                "snapshot_date": date_key,
                "trade_date": date_key,
                "status": "running",
                "job_id": db_job.get("job_id"),
                "current_step": "pipeline",
                "progress": pipeline_progress("pipeline"),
                "daily_status": "running",
                "cockpit_light": "blue",
                "headline": f"Updating {date_key}…",
                "pipeline": {},
            }

        validation = build_validation_from_storage(storage, config=config, snapshot_date=date_key)
        overall = validation.get("overall", "idle")
        run_status = str((run or {}).get("status") or "")
        if run_status == "failed":
            daily_status = "failed"
            status = "failed"
        elif overall in {"ready", "degraded"}:
            daily_status = overall
            status = "done"
        elif storage.get_snapshot(date_key):
            daily_status = overall if overall != "idle" else "degraded"
            status = "done"
        else:
            daily_status = "idle"
            status = "idle"

        return {
            "snapshot_date": date_key,
            "trade_date": date_key,
            "status": status,
            "daily_status": daily_status,
            "cockpit_light": validation.get("cockpit_light", "gray"),
            "headline": validation.get("headline"),
            "error": (run or {}).get("error"),
            "pipeline": {"steps": validation.get("steps", {})},
            "run_status": run,
        }

    def build_dashboard(
        self,
        storage: Storage,
        config: dict[str, Any],
        snapshot_date: str | None = None,
    ) -> dict[str, Any]:
        target_date = latest_trading_date()
        display_date = self.resolve_display_date(storage, snapshot_date)
        status = self.get_status(storage, config, target_date)
        db_check = check_db(storage)
        proxy_check = check_proxy(config)
        lag_days = _stale_days(display_date, target_date) if display_date else 0
        headline = status.get("headline")
        if lag_days > 0 and status.get("daily_status") != "running":
            headline = f"Showing {display_date} · target {target_date} ({lag_days}d behind, catching up)"
        elif lag_days > 0 and status.get("daily_status") == "running":
            headline = f"Updating {target_date}… (displaying {display_date})"

        top_strong_count = 0
        watchlist_count = 0
        rows = storage.get_snapshot(display_date)
        if rows:
            top_n = int(config.get("thresholds", {}).get("top_list_count", 10))
            top_strong_count = len(top_strong_from_rows(rows, top_n=top_n))
            watchlist_count = storage.count_stock_watchlist(display_date)

        breadth_latest = None
        breadth_rows = storage.get_breadth_daily(limit=1)
        if breadth_rows:
            breadth_latest = breadth_rows[0].get("trade_date") or breadth_rows[0].get("raw_date")

        rs_count = storage.count_stock_rs(display_date) if rows else 0
        progress = pipeline_progress(status.get("current_step"))
        env_health = "ok" if db_check.get("ok") else "degraded"
        return {
            "trade_date": target_date,
            "target_date": target_date,
            "display_date": display_date,
            "lag_days": lag_days,
            "has_snapshot": bool(rows),
            "daily_status": status.get("daily_status", "idle"),
            "cockpit_light": status.get("cockpit_light", "gray"),
            "headline": headline,
            "current_step": status.get("current_step"),
            "progress": progress,
            "summary": {
                "top_strong_count": top_strong_count,
                "watchlist_count": watchlist_count,
                "rs_count": rs_count,
                "industry_count": len(rows) if rows else 0,
            },
            "environment": {
                "health": env_health,
                "proxy_ok": bool(proxy_check.get("ok")),
                "finviz_ok": None,
                "breadth_ok": bool(breadth_rows),
                "breadth_latest_date": breadth_latest,
            },
            "pipeline": status.get("pipeline") or {},
            "status": status.get("status"),
            "error": status.get("error"),
            "top_strong": [],
            "watchlist": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _status_payload(
        self,
        date_key: str,
        memory: dict[str, Any],
        storage: Storage,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        run = storage.get_snapshot_run(date_key)
        validation = (run or {}).get("details") or {}
        if isinstance(validation, dict):
            validation = validation.get("validation") or {}
        steps = validation.get("steps") if isinstance(validation, dict) else {}
        return {
            "snapshot_date": date_key,
            "trade_date": date_key,
            "status": "running",
            "job_id": memory.get("job_id"),
            "current_step": memory.get("current_step") or (run or {}).get("current_step"),
            "daily_status": "running",
            "cockpit_light": "blue",
            "headline": f"Updating {date_key}…",
            "pipeline": {"steps": steps or {}},
        }

    @staticmethod
    def _summary_details(result: dict[str, Any]) -> dict[str, Any]:
        rs = result.get("rs") or {}
        breadth = result.get("breadth") or {}
        return {
            "industry_count": result.get("industry_count"),
            "top_count": result.get("top_count"),
            "stock_pick_count": result.get("stock_pick_count"),
            "stock_pick_errors": result.get("stock_pick_errors"),
            "rs_computed_count": rs.get("computed_count"),
            "breadth_merged_count": breadth.get("merged_row_count"),
        }
