import { useEffect, useState } from "react";
import { fetchJson, IS_READONLY } from "../../lib/api";

type HealthStatus = "ok" | "degraded" | "error" | "loading";

const HEALTH_STYLES: Record<
  Exclude<HealthStatus, "loading">,
  { wrap: string; text: string; dot: string; ping: boolean }
> = {
  ok: {
    wrap: "bg-emerald-950/30 border-emerald-900/50 shadow-[0_0_10px_rgba(16,185,129,0.05)]",
    text: "text-emerald-500",
    dot: "bg-emerald-500",
    ping: true,
  },
  degraded: {
    wrap: "bg-amber-950/30 border-amber-900/50 shadow-[0_0_10px_rgba(245,158,11,0.05)]",
    text: "text-amber-500",
    dot: "bg-amber-500",
    ping: true,
  },
  error: {
    wrap: "bg-rose-950/30 border-rose-900/50",
    text: "text-rose-500",
    dot: "bg-rose-500",
    ping: false,
  },
};

export function TerminalHealthIndicator() {
  const [status, setStatus] = useState<HealthStatus>("loading");
  const [label, setLabel] = useState("Checking");
  const [title, setTitle] = useState("");

  useEffect(() => {
    fetchJson<{
      status?: string;
      checks?: Record<string, { ok?: boolean }>;
    }>("/api/health?quick=1")
      .then((health) => {
        const raw = health.status || "error";
        const checks = health.checks || {};
        const bad = Object.entries(checks)
          .filter(([, v]) => !v?.ok)
          .map(([k]) => k)
          .join(", ");
        const next: HealthStatus =
          raw === "ok" ? "ok" : raw === "degraded" ? "degraded" : "error";
        const text =
          next === "ok"
            ? IS_READONLY
              ? "Snapshot OK"
              : "Healthy"
            : next === "degraded"
              ? "Degraded"
              : "Error";
        setStatus(next);
        setLabel(text);
        setTitle(
          bad
            ? `Failed checks: ${bad}`
            : IS_READONLY
              ? "Read-only published snapshot"
              : "All checks passed",
        );
      })
      .catch((err) => {
        setStatus("error");
        setLabel("Offline");
        setTitle(err instanceof Error ? err.message : "health api failed");
      });
  }, []);

  if (status === "loading") {
    return (
      <div
        className="flex items-center gap-2 bg-slate-900/50 border border-slate-800 px-3 py-1 rounded-full"
        role="status"
        aria-live="polite"
      >
        <span className="w-2 h-2 rounded-full bg-slate-600 animate-pulse" />
        <span className="text-[10px] font-mono text-slate-500 font-bold uppercase tracking-widest leading-none mt-px">
          Checking
        </span>
      </div>
    );
  }

  const ui = HEALTH_STYLES[status];

  return (
    <div
      className={`flex items-center gap-2 border px-3 py-1 rounded-full ${ui.wrap}`}
      role="status"
      aria-live="polite"
      title={title}
      aria-label={title ? `${label}. ${title}` : label}
    >
      <span className="relative flex h-2 w-2">
        {ui.ping ? (
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${ui.dot}`}
          />
        ) : null}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${ui.dot}`} />
      </span>
      <span
        className={`text-[10px] font-mono font-bold uppercase tracking-widest leading-none mt-px ${ui.text}`}
      >
        {label}
      </span>
    </div>
  );
}
