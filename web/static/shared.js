function showToast(message, isError = false) {
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
  clearTimeout(el._timer);
  el._timer = setTimeout(() => {
    if (el) {
      el.textContent = "";
      el.style.display = "none";
      el.classList.remove("is-error");
    }
  }, 4200);
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    if (err && typeof err === "object" && (err.code || err.message || err.hint)) {
      const parts = [err.message || res.statusText];
      if (err.hint) parts.push(`Hint: ${err.hint}`);
      if (err.code) parts.push(`(${err.code})`);
      const message = parts.filter(Boolean).join(" ");
      throw new Error(message);
    }
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join("; ")
      : detail || res.statusText;
    throw new Error(message);
  }
  return res.json();
}

function healthBadgeClass(status) {
  if (status === "ok") return "health-badge ok";
  if (status === "degraded") return "health-badge degraded";
  return "health-badge error";
}

async function renderHealthBadge(targetId = "healthBadge", { quick = true } = {}) {
  const el = document.getElementById(targetId);
  if (!el) return;
  try {
    const health = await fetchJson(`/api/health${quick ? "?quick=1" : ""}`);
    const status = health.status || "error";
    const checks = health.checks || {};
    const bad = Object.entries(checks)
      .filter(([, v]) => !v?.ok)
      .map(([k]) => k)
      .join(", ");
    const label =
      status === "ok" ? "Healthy" : status === "degraded" ? "Degraded" : "Error";
    el.className = healthBadgeClass(status);
    el.textContent = label;
    el.title = bad ? `Failed checks: ${bad}` : "All checks passed";
    el.setAttribute("aria-label", bad ? `${label}. Failed checks: ${bad}` : `${label}. All checks passed`);
  } catch (err) {
    el.className = "health-badge error";
    el.textContent = "Health check failed";
    el.title = err.message || "health api failed";
    el.setAttribute("aria-label", `Health check failed: ${err.message || "health api failed"}`);
  }
}

function bjDateKey() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function bjHourNow() {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const hourPart = parts.find((p) => p.type === "hour");
  return Number(hourPart?.value || 0);
}

function readCssVar(name, fallback = "") {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function chartThemeFromCss() {
  return {
    accent: readCssVar("--accent", "#a8b0bc"),
    text: readCssVar("--chart-text", "#8a8a96"),
    grid: readCssVar("--chart-grid", "rgba(255,255,255,0.05)"),
    ok: readCssVar("--ok", "#5a9a6e"),
    bad: readCssVar("--bad", "#9a5a5a"),
    warn: readCssVar("--warn", "#9a8a58"),
    muted: readCssVar("--accent-muted", "#787882"),
  };
}
