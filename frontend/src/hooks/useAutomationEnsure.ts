import { useEffect, useRef } from "react";
import { fetchJson, IS_READONLY } from "../lib/api";
import type { AutomationStatus } from "../lib/industry";

export function needsAutomationEnsure(status: AutomationStatus): boolean {
  if (!status.has_snapshot) return true;
  if ((status.lag_days ?? 0) > 0) return true;
  const daily = status.daily_status || "";
  return daily === "idle" || daily === "failed";
}

async function postAutomationEnsure(): Promise<void> {
  await fetchJson("/api/automation/ensure", { method: "POST" });
}

export function useAutomationEnsure() {
  const requestedRef = useRef(false);

  useEffect(() => {
    if (IS_READONLY || requestedRef.current) return;
    requestedRef.current = true;

    (async () => {
      try {
        const status = await fetchJson<AutomationStatus>("/api/automation/status");
        if (!needsAutomationEnsure(status)) return;
        await postAutomationEnsure();
      } catch {
        // Server offline — use desktop Open US Industry Strength.app or wait for launchd.
      }
    })();
  }, []);
}

export function useAutomationEnsureOnStale(status: AutomationStatus | null) {
  const lastTriggerRef = useRef("");

  useEffect(() => {
    if (IS_READONLY || !status || !needsAutomationEnsure(status)) return;
    const key = `${status.target_date}:${status.daily_status}:${status.lag_days}`;
    if (lastTriggerRef.current === key) return;
    lastTriggerRef.current = key;
    postAutomationEnsure().catch(() => {});
  }, [status]);
}
