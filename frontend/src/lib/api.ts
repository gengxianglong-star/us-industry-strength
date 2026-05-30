let toastTimer: ReturnType<typeof setTimeout> | undefined;

export const IS_READONLY = import.meta.env.VITE_READONLY === "1";
const DATA_BASE = `${import.meta.env.BASE_URL}data/`;

export function showToast(message: string, isError = false): void {
  let el = document.getElementById("globalToast");
  if (!el) {
    el = document.createElement("div");
    el.id = "globalToast";
    el.className = "global-toast";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.setAttribute("aria-atomic", "true");
    document.body.appendChild(el);
  }
  if (!message) {
    el.style.display = "none";
    el.textContent = "";
    el.classList.remove("is-error");
    return;
  }
  el.style.display = "block";
  el.textContent = message;
  el.classList.toggle("is-error", Boolean(isError));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    if (el) {
      el.textContent = "";
      el.style.display = "none";
      el.classList.remove("is-error");
    }
  }, 4200);
}

function staticDataUrl(apiUrl: string): string | null {
  const [path, query = ""] = apiUrl.split("?");
  if (path === "/api/snapshots/latest" || /^\/api\/snapshots\/\d{4}-\d{2}-\d{2}$/.test(path)) {
    return `${DATA_BASE}snapshot.json`;
  }
  if (path === "/api/automation/status") {
    return `${DATA_BASE}automation.json`;
  }
  if (path.startsWith("/api/rs/")) {
    return query.includes("watchlist_only=true") ? `${DATA_BASE}rs_watchlist.json` : `${DATA_BASE}rs.json`;
  }
  if (path === "/api/breadth") {
    return `${DATA_BASE}breadth.json`;
  }
  if (path === "/api/breadth/config") {
    return `${DATA_BASE}breadth_config.json`;
  }
  if (path.startsWith("/api/health")) {
    return `${DATA_BASE}health.json`;
  }
  if (path === "/api/breadth/sync-progress") {
    return `${DATA_BASE}sync_progress.json`;
  }
  return null;
}

async function fetchStaticJson<T>(apiUrl: string): Promise<T> {
  const staticUrl = staticDataUrl(apiUrl);
  if (!staticUrl) {
    throw new Error(`Read-only mode: unsupported request ${apiUrl}`);
  }
  const res = await fetch(staticUrl);
  if (!res.ok) {
    throw new Error(`Static data missing (${res.status}): ${staticUrl}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchJson<T = unknown>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  if (IS_READONLY) {
    const method = (options.method || "GET").toUpperCase();
    if (method !== "GET") {
      throw new Error("Read-only dashboard — changes are not saved");
    }
    return fetchStaticJson<T>(url);
  }

  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (err && typeof err === "object" && (err.code || err.message || err.hint)) {
      const parts = [String(err.message || res.statusText)];
      if (err.hint) parts.push(`Hint: ${err.hint}`);
      if (err.code) parts.push(`(${err.code})`);
      throw new Error(parts.filter(Boolean).join(" "));
    }
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).join("; ")
      : detail || res.statusText;
    throw new Error(String(message));
  }
  return res.json() as Promise<T>;
}

export function healthBadgeClass(status: string): string {
  if (status === "ok") return "health-badge ok";
  if (status === "degraded") return "health-badge degraded";
  return "health-badge error";
}

export async function loadHealthBadge(
  target: HTMLElement | null,
  { quick = true }: { quick?: boolean } = {},
): Promise<void> {
  if (!target) return;
  try {
    const health = await fetchJson<{
      status?: string;
      checks?: Record<string, { ok?: boolean }>;
    }>(`/api/health${quick ? "?quick=1" : ""}`);
    const status = health.status || "error";
    const checks = health.checks || {};
    const bad = Object.entries(checks)
      .filter(([, v]) => !v?.ok)
      .map(([k]) => k)
      .join(", ");
    const label =
      status === "ok"
        ? IS_READONLY
          ? "Snapshot OK"
          : "Healthy"
        : status === "degraded"
          ? "Degraded"
          : "Error";
    target.className = healthBadgeClass(status);
    target.textContent = label;
    target.title = bad ? `Failed checks: ${bad}` : IS_READONLY ? "Read-only published snapshot" : "All checks passed";
    target.setAttribute(
      "aria-label",
      bad ? `${label}. Failed checks: ${bad}` : `${label}. All checks passed`,
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "health api failed";
    target.className = "health-badge error";
    target.textContent = "Health check failed";
    target.title = message;
    target.setAttribute("aria-label", `Health check failed: ${message}`);
  }
}

export function bjDateKey(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function bjHourNow(): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const hourPart = parts.find((p) => p.type === "hour");
  return Number(hourPart?.value || 0);
}
