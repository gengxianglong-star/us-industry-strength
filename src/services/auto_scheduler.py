"""Background automation: scheduled daily runs, startup catch-up, and watchdog retries."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.logging_config import get_logger
from src.services.breadth_jobs import BREADTH_JOB_KIND, BREADTH_JOB_SCOPE, BreadthSyncService
from src.services.daily_jobs import DailyJobService
from src.services.daily_validation import _latest_breadth_trade_date, _stale_days
from src.services.rs_jobs import RsJobService
from src.services.snapshots import scored_industries_from_rows
from src.storage import Storage, latest_trading_date

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = ROOT / "data" / "automation_state.json"


def automation_settings(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("automation") or {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "timezone": str(raw.get("timezone") or "Asia/Shanghai"),
        "daily_hour": int(raw.get("daily_hour", 6)),
        "daily_minute": int(raw.get("daily_minute", 30)),
        "weekdays_only": bool(raw.get("weekdays_only", True)),
        "run_on_startup": bool(raw.get("run_on_startup", True)),
        "watchdog_interval_minutes": int(raw.get("watchdog_interval_minutes", 20)),
        "retry_failed": bool(raw.get("retry_failed", True)),
        "retry_failed_rs": bool(raw.get("retry_failed_rs", raw.get("retry_failed", True))),
        "auto_install_service": bool(raw.get("auto_install_service", True)),
        "catchup_interval_minutes": int(raw.get("catchup_interval_minutes", 2)),
    }


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now().astimezone().isoformat()
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class AutoScheduler:
    TICK_SECONDS = 60

    def __init__(
        self,
        *,
        storage: Storage,
        config_getter: Callable[[], dict[str, Any]],
        daily_service: DailyJobService,
        rs_service: RsJobService | None = None,
        breadth_service: BreadthSyncService | None = None,
    ) -> None:
        self._storage = storage
        self._config_getter = config_getter
        self._daily_service = daily_service
        self._rs_service = rs_service or RsJobService()
        self._breadth_service = breadth_service or BreadthSyncService()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_watchdog_ts = 0.0
        self._last_catchup_ts = 0.0

    def update_storage(self, storage: Storage) -> None:
        self._storage = storage

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._maybe_install_service()
        self._thread = threading.Thread(target=self._loop, name="auto-scheduler", daemon=True)
        self._thread.start()
        if automation_settings(self._config_getter()).get("run_on_startup"):
            threading.Thread(target=self._startup_catchup, name="auto-startup", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        cfg = automation_settings(self._config_getter())
        state = _load_state()
        trade_date = latest_trading_date()
        display_date = self._storage.get_latest_date()
        lag_days = _stale_days(display_date, trade_date) if display_date else 0
        run = self._storage.get_snapshot_run(trade_date)
        db_job = self._storage.get_latest_rs_job_run(trade_date, job_kind="daily")
        rs_job = self._storage.get_latest_rs_job_run(trade_date, job_kind="main")
        run_state = str((run or {}).get("status") or "")
        job_state = str((db_job or {}).get("status") or "")
        rs_state = str((rs_job or {}).get("status") or "")
        if run_state == "running" or job_state == "running" or rs_state == "running":
            daily_status = "running"
            headline = (
                f"RS running · {trade_date}…"
                if rs_state == "running" and run_state != "running"
                else f"Updating {trade_date}…"
            )
        elif run_state == "failed":
            daily_status = "failed"
            headline = str((run or {}).get("error") or "Update failed")
        elif self._storage.get_snapshot(trade_date):
            validation = ((run or {}).get("details") or {}).get("validation") if run else None
            if isinstance(validation, dict):
                daily_status = validation.get("overall", "degraded")
                headline = validation.get("headline")
            else:
                daily_status = "degraded"
                headline = f"As of {trade_date} (cached snapshot)"
        else:
            daily_status = "idle"
            headline = f"No data for {trade_date} yet"
        if lag_days > 0 and daily_status == "running":
            headline = f"Updating {trade_date}… (displaying {display_date})"
        elif lag_days > 0 and daily_status in {"idle", "failed"}:
            headline = f"Showing {display_date} · target {trade_date} ({lag_days}d behind, auto catch-up queued)"
        return {
            "enabled": cfg["enabled"],
            "timezone": cfg["timezone"],
            "schedule": f"{cfg['daily_hour']:02d}:{cfg['daily_minute']:02d}",
            "weekdays_only": cfg["weekdays_only"],
            "state": state,
            "trade_date": trade_date,
            "target_date": trade_date,
            "display_date": display_date,
            "lag_days": lag_days,
            "has_snapshot": bool(display_date),
            "daily_status": daily_status,
            "headline": headline,
            "running": bool(self._thread and self._thread.is_alive()),
        }

    def _maybe_install_service(self) -> None:
        cfg = automation_settings(self._config_getter())
        if not cfg.get("auto_install_service") or sys.platform != "darwin":
            return
        marker = Path.home() / "Library/LaunchAgents/com.us-industry-strength.server.plist"
        if marker.exists():
            return
        script = ROOT / "scripts" / "install-automation.sh"
        if not script.exists():
            return
        try:
            subprocess.run(["/bin/bash", str(script)], cwd=str(ROOT), check=False, timeout=120)
            logger.info("attempted first-run service install (macOS launchd)")
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.info("service install skipped: %s", exc)

    def ensure_now(self, *, reason: str = "browser") -> dict[str, Any]:
        """Trigger catch-up / retry when the dashboard is opened (idempotent)."""
        cfg = automation_settings(self._config_getter())
        if not cfg["enabled"]:
            return {"triggered": ["disabled"], **self.status()}

        trade_date = latest_trading_date()
        display_date = self._storage.get_latest_date()
        lag_days = _stale_days(display_date, trade_date) if display_date else 999
        daily = self._daily_service.get_status(self._storage, self._config_getter(), trade_date)
        daily_status = str(daily.get("daily_status") or "")
        triggered: list[str] = []

        if daily_status == "running":
            triggered.append("already_running")
        elif lag_days > 0 or not self._storage.get_snapshot(trade_date):
            self._ensure_daily(reason=reason, force_catchup=True)
            triggered.append("daily_catchup")
        elif daily_status in {"failed", "idle"}:
            self._ensure_daily(reason=reason)
            triggered.append("daily_retry" if daily_status == "failed" else "daily_start")
        else:
            triggered.append("daily_ok")

        if daily_status != "running":
            before_rs = self._rs_needs_work(trade_date)
            before_breadth = self._breadth_needs_work(trade_date)
            self._ensure_rs_if_needed(trade_date, cfg)
            self._ensure_breadth_if_needed(trade_date)
            if before_rs:
                triggered.append("rs_recovery")
            if before_breadth:
                triggered.append("breadth_sync")

        return {"triggered": triggered, **self.status()}

    def schedule_recovery(self, *, reason: str, delay_seconds: float = 5) -> None:
        def _run() -> None:
            time.sleep(delay_seconds)
            cfg = automation_settings(self._config_getter())
            if not cfg["enabled"]:
                return
            trade_date = latest_trading_date()
            self._ensure_daily(reason=reason, force_catchup=True)
            self._ensure_rs_if_needed(trade_date, cfg)

        threading.Thread(target=_run, name=f"auto-recover-{reason}", daemon=True).start()

    def _startup_catchup(self) -> None:
        time.sleep(1)
        cfg = automation_settings(self._config_getter())
        if not cfg["enabled"]:
            return
        trade_date = latest_trading_date()
        display_date = self._storage.get_latest_date()
        lag_days = _stale_days(display_date, trade_date) if display_date else 999
        if lag_days > 0:
            self._ensure_daily(reason="startup", force_catchup=True)
        self._ensure_rs_if_needed(trade_date, cfg)
        self._ensure_breadth_if_needed(trade_date)

    def _loop(self) -> None:
        while not self._stop.wait(self.TICK_SECONDS):
            cfg = automation_settings(self._config_getter())
            if not cfg["enabled"]:
                continue
            now = self._now(cfg)
            if self._should_run_schedule(now, cfg):
                self._mark_scheduled(latest_trading_date())
                self._ensure_daily(reason="schedule")
            trade_date = latest_trading_date()
            display_date = self._storage.get_latest_date()
            lag_days = _stale_days(display_date, trade_date) if display_date else 999
            if lag_days > 0 and self._catchup_due(cfg):
                self._ensure_daily(reason="catchup", force_catchup=True)
                self._ensure_rs_if_needed(trade_date, cfg)
                self._ensure_breadth_if_needed(trade_date)
            elif self._watchdog_due(cfg):
                self._watchdog_tick(cfg)

    def _catchup_due(self, cfg: dict[str, Any]) -> bool:
        interval = max(1, int(cfg.get("catchup_interval_minutes", 2))) * 60
        now_ts = time.time()
        if now_ts - self._last_catchup_ts < interval:
            return False
        self._last_catchup_ts = now_ts
        return True

    def _watchdog_due(self, cfg: dict[str, Any]) -> bool:
        interval = max(5, int(cfg.get("watchdog_interval_minutes", 20))) * 60
        now_ts = time.time()
        if now_ts - self._last_watchdog_ts < interval:
            return False
        self._last_watchdog_ts = now_ts
        return True

    def _watchdog_tick(self, cfg: dict[str, Any]) -> None:
        trade_date = latest_trading_date()
        display_date = self._storage.get_latest_date()
        lag_days = _stale_days(display_date, trade_date) if display_date else 999

        self._ensure_rs_if_needed(trade_date, cfg)
        self._ensure_breadth_if_needed(trade_date)

        if lag_days > 0:
            self._ensure_daily(reason="watchdog", force_catchup=True)
            return

        daily = self._daily_service.get_status(self._storage, self._config_getter(), trade_date)
        status = str(daily.get("daily_status") or "")
        if status == "running":
            return
        if status in {"ready", "degraded"}:
            return
        if status == "failed" and not cfg.get("retry_failed"):
            return
        self._ensure_daily(reason="watchdog")

    def _rs_needs_work(self, trade_date: str) -> bool:
        if not self._storage.get_snapshot(trade_date):
            return False
        rs_job = self._storage.get_latest_rs_job_run(trade_date, job_kind="main")
        rs_state = str((rs_job or {}).get("status") or "")
        if rs_state == "running":
            return False
        if rs_state in {"error", "cancelled"}:
            return True
        meta = self._storage.get_stock_rs_meta(trade_date) or {}
        computed = int(meta.get("computed_count") or 0)
        coverage = float(meta.get("coverage_ratio") or 0.0)
        no_bars = int(meta.get("no_bars_count") or 0)
        universe = int(meta.get("universe_count") or 0)
        no_bars_ratio = (no_bars / universe) if universe else 1.0
        if rs_state == "done" and computed >= 200 and coverage >= 0.02:
            if no_bars_ratio < 0.08 and no_bars < 500:
                return False
            return True
        return computed < 200 or coverage < 0.02

    def _ensure_rs_if_needed(self, trade_date: str, cfg: dict[str, Any] | None = None) -> None:
        cfg = cfg or automation_settings(self._config_getter())
        if not cfg.get("retry_failed_rs", True):
            return
        if not self._rs_needs_work(trade_date):
            return
        rows = self._storage.get_snapshot(trade_date)
        if not rows:
            return
        scored = scored_industries_from_rows(rows)
        result = self._rs_service.start_compute_rs(
            storage=self._storage,
            snapshot_date=trade_date,
            scored=scored,
            config=self._config_getter(),
            force_full=False,
            async_mode=True,
        )
        state = _load_state()
        state["last_rs_recovery"] = {
            "trade_date": trade_date,
            "at": datetime.now().astimezone().isoformat(),
            "result_status": result.get("status"),
        }
        _save_state(state)
        logger.info("RS recovery (%s) -> %s", trade_date, result.get("status"))

    def _breadth_automation_enabled(self) -> bool:
        daily = (self._config_getter().get("automation") or {}).get("daily") or {}
        return not bool(daily.get("skip_breadth", True))

    def _breadth_needs_work(self, trade_date: str) -> bool:
        if not self._breadth_automation_enabled():
            return False
        latest = _latest_breadth_trade_date(self._storage)
        if _stale_days(latest, trade_date) <= 0:
            return False
        db_job = self._storage.get_latest_rs_job_run(BREADTH_JOB_SCOPE, job_kind=BREADTH_JOB_KIND)
        if db_job and str(db_job.get("status") or "") in {"running", "cancelling"}:
            return False
        if str(self._breadth_service.get_state().get("status") or "") == "running":
            return False
        return True

    def _ensure_breadth_if_needed(self, trade_date: str) -> None:
        if not self._breadth_needs_work(trade_date):
            return
        result = self._breadth_service.start_sync(self._storage, full=False, async_mode=True)
        state = _load_state()
        state["last_breadth_sync"] = {
            "trade_date": trade_date,
            "at": datetime.now().astimezone().isoformat(),
            "result_status": result.get("status"),
        }
        _save_state(state)
        logger.info("breadth sync (%s) -> %s", trade_date, result.get("status"))

    def _ensure_daily(self, *, reason: str, force_catchup: bool = False) -> None:
        cfg = automation_settings(self._config_getter())
        if not cfg["enabled"]:
            return
        config = self._config_getter()
        trade_date = latest_trading_date()
        daily = self._daily_service.get_status(self._storage, config, trade_date)
        status = str(daily.get("daily_status") or "")
        latest_snap = self._storage.get_latest_date()
        needs_catchup = (
            not self._storage.get_snapshot(trade_date)
            or (
                isinstance(latest_snap, str)
                and latest_snap
                and latest_snap < trade_date
            )
            or (force_catchup and latest_snap and latest_snap < trade_date)
        )

        if status == "running":
            return
        if needs_catchup:
            pass
        elif status in {"ready", "degraded"} and reason in {"startup", "schedule", "watchdog", "catchup"}:
            return
        if status == "failed" and reason == "watchdog" and not cfg.get("retry_failed"):
            return

        force = needs_catchup or status == "failed"
        result = self._daily_service.start_run(
            self._storage,
            config,
            trade_date,
            force=force,
            async_mode=True,
        )
        state = _load_state()
        state["last_trigger"] = {
            "reason": reason,
            "trade_date": trade_date,
            "at": datetime.now().astimezone().isoformat(),
            "result_status": result.get("status"),
        }
        if reason == "schedule":
            state["last_scheduled_run"] = trade_date
        _save_state(state)
        logger.info("daily triggered (%s) -> %s", reason, result.get("status"))

    def _should_run_schedule(self, now: datetime, cfg: dict[str, Any]) -> bool:
        if cfg.get("weekdays_only") and now.weekday() >= 5:
            return False
        if now.hour != int(cfg["daily_hour"]) or now.minute != int(cfg["daily_minute"]):
            return False
        trade_date = latest_trading_date()
        state = _load_state()
        if state.get("last_scheduled_run") == trade_date:
            return False
        return True

    def _mark_scheduled(self, trade_date: str) -> None:
        state = _load_state()
        state["last_scheduled_run"] = trade_date
        _save_state(state)

    @staticmethod
    def _now(cfg: dict[str, Any]) -> datetime:
        tz_name = str(cfg.get("timezone") or "Asia/Shanghai")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            logger.debug("invalid timezone '%s', falling back to Asia/Shanghai", tz_name)
            tz = ZoneInfo("Asia/Shanghai")
        return datetime.now(tz)
