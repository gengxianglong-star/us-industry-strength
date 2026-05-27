function showToast(message, isError = false) {
  let el = document.getElementById("globalToast");
  if (!el) {
    el = document.createElement("div");
    el.id = "globalToast";
    el.style.position = "fixed";
    el.style.right = "18px";
    el.style.bottom = "18px";
    el.style.maxWidth = "460px";
    el.style.padding = "10px 14px";
    el.style.borderRadius = "8px";
    el.style.fontSize = "13px";
    el.style.zIndex = "9999";
    el.style.boxShadow = "0 6px 20px rgba(0,0,0,0.35)";
    document.body.appendChild(el);
  }
  if (!message) {
    el.style.display = "none";
    el.textContent = "";
    return;
  }
  el.style.display = "block";
  el.textContent = message;
  el.style.background = isError ? "rgba(153,27,27,0.95)" : "rgba(30,58,138,0.95)";
  el.style.color = "#fff";
  clearTimeout(el._timer);
  el._timer = setTimeout(() => {
    if (el) {
      el.textContent = "";
      el.style.display = "none";
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
    const detail = err.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join("; ")
      : detail || res.statusText;
    throw new Error(message);
  }
  return res.json();
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
