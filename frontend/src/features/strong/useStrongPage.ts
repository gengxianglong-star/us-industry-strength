import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJson, IS_READONLY } from "../../lib/api";
import { useAutomationEnsureOnStale } from "../../hooks/useAutomationEnsure";
import {
  getTopStrongIndustries,
  type AutomationStatus,
  type RsPayload,
  type SnapshotPayload,
} from "../../lib/industry";

export function useStrongPage() {
  const [snapshot, setSnapshot] = useState<SnapshotPayload | null>(null);
  const [rsPayload, setRsPayload] = useState<RsPayload | null>(null);
  const [automation, setAutomation] = useState<AutomationStatus | null>(null);
  const [rsStatus, setRsStatus] = useState("");
  const [rsStatusError, setRsStatusError] = useState(false);
  const [search, setSearch] = useState("");
  const [topListCount, setTopListCount] = useState(10);
  const busyRef = useRef(false);

  const applyAutoStatus = useCallback((dashboard: AutomationStatus) => {
    const headline = dashboard.headline || "";
    const isError = dashboard.daily_status === "failed";
    const isRunning = dashboard.daily_status === "running";
    if (isRunning) {
      setRsStatus(headline || "Updating…");
      setRsStatusError(false);
    } else if (headline) {
      setRsStatus(headline);
      setRsStatusError(isError);
    } else if (dashboard.daily_status === "ready" || dashboard.daily_status === "degraded") {
      setRsStatus("Data ready");
      setRsStatusError(false);
    }
  }, []);

  const loadDecisionView = useCallback(async (date: string, snap?: SnapshotPayload) => {
    const snapshotData =
      snap ?? (await fetchJson<SnapshotPayload>(`/api/snapshots/${encodeURIComponent(date)}`));

    const rsWatch = await fetchJson<{
      watchlist?: RsPayload["watchlist"];
      rs_meta?: RsPayload["rs_meta"];
    }>(`/api/rs/${encodeURIComponent(date)}?watchlist_only=true&watchlist_limit=120`).catch(() => null);

    setSnapshot({
      ...snapshotData,
      rs_meta: rsWatch?.rs_meta || snapshotData.rs_meta,
    });
    setTopListCount(snapshotData.top_strong_count ?? getTopStrongIndustries(snapshotData).length);
    const watchlistRows = rsWatch?.watchlist || snapshotData.watchlist_preview || [];
    setRsPayload({
      snapshot_date: date,
      rows: [],
      watchlist: watchlistRows,
      new_stock_leaderboard: [],
      rs_meta: rsWatch?.rs_meta || snapshotData.rs_meta,
    });
  }, []);

  const refreshFromServer = useCallback(async () => {
    const [snapshotResult, statusResult] = await Promise.allSettled([
      fetchJson<SnapshotPayload>("/api/snapshots/latest"),
      fetchJson<AutomationStatus>("/api/automation/status"),
    ]);

    if (statusResult.status === "fulfilled") {
      setAutomation(statusResult.value);
      applyAutoStatus(statusResult.value);
    }

    if (snapshotResult.status === "fulfilled") {
      const snap = snapshotResult.value;
      await loadDecisionView(snap.snapshot_date, snap);
      return statusResult.status === "fulfilled" ? statusResult.value : null;
    }

    if (statusResult.status === "fulfilled" && !statusResult.value.has_snapshot) {
      setRsStatus("Waiting for first update");
      setRsStatusError(false);
    }
    return statusResult.status === "fulfilled" ? statusResult.value : null;
  }, [applyAutoStatus, loadDecisionView]);

  const watchAutomation = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    try {
      const status = await fetchJson<AutomationStatus>("/api/automation/status");
      setAutomation(status);
      applyAutoStatus(status);
      const displayDate = status.display_date;
      if (displayDate && displayDate !== snapshot?.snapshot_date) {
        await loadDecisionView(displayDate);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Status check failed";
      setRsStatus(`Status check failed: ${message}`);
      setRsStatusError(true);
    } finally {
      busyRef.current = false;
    }
  }, [applyAutoStatus, loadDecisionView, snapshot?.snapshot_date]);

  useEffect(() => {
    refreshFromServer().catch(() => {});
    if (IS_READONLY) return undefined;
    const timer = window.setInterval(() => {
      watchAutomation().catch(() => {});
    }, 30000);
    return () => window.clearInterval(timer);
  }, [refreshFromServer, watchAutomation]);

  const watchlist =
    rsPayload?.watchlist?.length ? rsPayload.watchlist : snapshot?.watchlist_preview || [];

  const pulseLine = (() => {
    if (!snapshot) return "Loading snapshot…";
    const top = getTopStrongIndustries(snapshot);
    let dateText = snapshot.snapshot_date || "—";
    const lag = Number(automation?.lag_days || 0);
    const target = automation?.target_date;
    if (lag > 0 && target && target !== snapshot.snapshot_date) {
      dateText = `${dateText} (catch-up ${target})`;
    }
    const hot = top
      .slice(0, 3)
      .map((r) => r.name.split(/[\s/&-]/)[0])
      .join(", ");
    const hotText = hot || "—";
    return `${dateText} · Focus ${watchlist.length} · Hot themes: ${hotText} · RS universe scanned`;
  })();

  const filteredIndustries = (snapshot?.industries || [])
    .filter((r) => !search.trim() || r.name.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => b.score - a.score);

  useAutomationEnsureOnStale(automation);

  return {
    snapshot,
    rsPayload,
    watchlist,
    automation,
    rsStatus,
    rsStatusError,
    search,
    setSearch,
    topListCount,
    pulseLine,
    filteredIndustries,
  };
}
