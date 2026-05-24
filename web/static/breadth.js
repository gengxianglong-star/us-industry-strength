let chartInstances = [];

function toNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function heatClass(index, row) {
  const n = toNum(row[`c${index}_num`]);
  if (n == null) return "heat-neutral";
  const up4 = toNum(row.c1_num);
  const down4 = toNum(row.c2_num);
  const up25q = toNum(row.c5_num);
  const down25q = toNum(row.c6_num);
  const up25m = toNum(row.c7_num);
  const down25m = toNum(row.c8_num);
  const up13 = toNum(row.c11_num);
  const down13 = toNum(row.c12_num);

  if (index === 1 || index === 2) {
    if (up4 != null && down4 != null) return up4 >= down4 ? "heat-green" : "heat-red";
    return "heat-neutral";
  }

  if (index === 3) {
    if (n >= 2.0) return "heat-green";
    if (n <= 0.8) return "heat-red";
    return "heat-neutral";
  }

  if (index === 4) {
    if (n >= 1.2) return "heat-green";
    if (n <= 0.9) return "heat-red";
    return "heat-neutral";
  }

  if (index === 5 || index === 6) {
    if (up25q != null && down25q != null) return up25q >= down25q ? "heat-green" : "heat-red";
    return "heat-neutral";
  }

  if (index === 7 || index === 8) {
    if (up25m != null && down25m != null) return up25m >= down25m ? "heat-green" : "heat-red";
    return "heat-neutral";
  }

  if (index === 9) {
    if (n >= 40) return "heat-red";
    if (n <= 20) return "heat-green";
    return "heat-neutral";
  }

  if (index === 10) {
    if (n <= 40) return "heat-green";
    if (n >= 70) return "heat-red";
    return "heat-neutral";
  }

  if (index === 11 || index === 12) {
    if (up13 != null && down13 != null) return up13 >= down13 ? "heat-green" : "heat-red";
    return "heat-neutral";
  }

  return "heat-neutral";
}

function renderTable(payload) {
  const thead = document.querySelector("#breadthTable thead");
  const tbody = document.querySelector("#breadthTable tbody");
  const headers = payload.headers || [];
  const groupHeaders = payload.group_headers || [];
  const rows = payload.rows || [];
  const groups = [];
  let idx = 0;
  while (idx < headers.length) {
    const raw = (groupHeaders[idx] || "").trim();
    const start = idx;
    idx += 1;
    while (idx < headers.length && !(groupHeaders[idx] || "").trim()) idx += 1;
    const end = idx;
    const title = raw || headers[start] || "指标";
    groups.push({ title, span: end - start });
  }

  const groupRow = groups.map((g) => `<th class="group-head" colspan="${g.span}">${g.title}</th>`).join("");
  const metricRow = headers.map((h) => `<th class="metric-head">${h || " "}</th>`).join("");
  thead.innerHTML = `<tr>${groupRow}</tr><tr>${metricRow}</tr>`;
  tbody.innerHTML = rows
    .map((row) => {
      const tds = [`<td class="cell-date">${row.raw_date || row.date}</td>`];
      for (let idx = 1; idx <= 15; idx += 1) {
        const key = `c${idx}`;
        tds.push(`<td class="${heatClass(idx, row)}">${row[key] ?? ""}</td>`);
      }
      return `<tr>${tds.join("")}</tr>`;
    })
    .join("");
}

function destroyCharts() {
  chartInstances.forEach((chart) => chart && chart.destroy());
  chartInstances = [];
}

function renderCharts(payload) {
  const rows = [...(payload.rows || [])].slice(0, 160).reverse();
  if (!rows.length) return;
  const labels = rows.map((r) => r.raw_date || r.date);
  destroyCharts();

  chartInstances.push(new Chart(document.getElementById("ratioChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "5 Day Ratio", data: rows.map((r) => toNum(r.c3_num)), borderColor: "#34d399", tension: 0.2, pointRadius: 0 },
        { label: "10 Day Ratio", data: rows.map((r) => toNum(r.c4_num)), borderColor: "#fbbf24", tension: 0.2, pointRadius: 0 },
        { label: "T2108", data: rows.map((r) => toNum(r.c14_num)), borderColor: "#60a5fa", tension: 0.2, pointRadius: 0, yAxisID: "y1" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#dbe7f5" } } },
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
        y1: { position: "right", ticks: { color: "#9fb2cc" }, grid: { drawOnChartArea: false } },
      },
    },
  }));

  chartInstances.push(new Chart(document.getElementById("upDown4Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Up 4%+", data: rows.map((r) => toNum(r.c1_num)), borderColor: "#22c55e", pointRadius: 0, tension: 0.2 },
        { label: "Down 4%+", data: rows.map((r) => toNum(r.c2_num)), borderColor: "#ef4444", pointRadius: 0, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#dbe7f5" } } },
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    },
  }));

  chartInstances.push(new Chart(document.getElementById("quarter25Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Up 25% Quarter", data: rows.map((r) => toNum(r.c5_num)), borderColor: "#22c55e", pointRadius: 0, tension: 0.2 },
        { label: "Down 25% Quarter", data: rows.map((r) => toNum(r.c6_num)), borderColor: "#ef4444", pointRadius: 0, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#dbe7f5" } } },
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    },
  }));

  chartInstances.push(new Chart(document.getElementById("month25Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Up 25% Month", data: rows.map((r) => toNum(r.c7_num)), borderColor: "#2dd4bf", pointRadius: 0, tension: 0.2 },
        { label: "Down 25% Month", data: rows.map((r) => toNum(r.c8_num)), borderColor: "#f97316", pointRadius: 0, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#dbe7f5" } } },
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    },
  }));

  chartInstances.push(new Chart(document.getElementById("extreme50Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Up 50% Month", data: rows.map((r) => toNum(r.c9_num)), borderColor: "#f59e0b", pointRadius: 0, tension: 0.2 },
        { label: "Down 50% Month", data: rows.map((r) => toNum(r.c10_num)), borderColor: "#ef4444", pointRadius: 0, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#dbe7f5" } } },
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    },
  }));

  chartInstances.push(new Chart(document.getElementById("spxBreadthChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "S&P", data: rows.map((r) => toNum((r.c15 || "").replace(",", ""))), borderColor: "#60a5fa", pointRadius: 0, tension: 0.2, yAxisID: "y" },
        { label: "Up 13%/34D", data: rows.map((r) => toNum(r.c11_num)), borderColor: "#22c55e", pointRadius: 0, tension: 0.2, yAxisID: "y1" },
        { label: "Down 13%/34D", data: rows.map((r) => toNum(r.c12_num)), borderColor: "#ef4444", pointRadius: 0, tension: 0.2, yAxisID: "y1" },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#dbe7f5" } } },
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { position: "left", ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
        y1: { position: "right", ticks: { color: "#9fb2cc" }, grid: { drawOnChartArea: false } },
      },
    },
  }));
}

async function loadBreadth(refresh = false) {
  const btn = document.getElementById("refreshBreadthBtn");
  btn.disabled = true;
  btn.textContent = "刷新中…";
  try {
    const payload = await fetchJson(`/api/breadth?limit=240${refresh ? "&refresh=true" : ""}`);
    renderTable(payload);
    renderCharts(payload);
    document.getElementById("breadthMeta").textContent = `记录数 ${payload.row_count}，展示 ${payload.rows.length}，更新时间 ${payload.updated_at}`;
    document.getElementById("explainLink").href = payload.notes?.indicators_explain_url || "https://stockbee.blogspot.com/2022/12/market-monitor-scans.html";
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "刷新宽度数据";
  }
}

function init() {
  const widthRange = document.getElementById("chartWidthRange");
  const widthValue = document.getElementById("chartWidthValue");
  const chartPanel = document.querySelector(".chart-panel");
  const setChartWidth = (val) => {
    widthValue.textContent = `${val}%`;
    chartPanel?.style.setProperty("--charts-width", `${val}%`);
  };
  setChartWidth(widthRange.value);
  widthRange.addEventListener("input", (e) => setChartWidth(e.target.value));

  document.getElementById("refreshBreadthBtn").addEventListener("click", () => {
    loadBreadth(true).catch((err) => alert(err.message));
  });
  loadBreadth(false).catch((err) => alert(err.message));
}

init();
