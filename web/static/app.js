let currentSnapshot = null;
let currentRsSnapshot = null;
let autoRefreshBusy = false;
let automationTimer = null;

const LEGACY_TAG_LABEL = {
  "核心强势": "Core",
  "不一致": "Mixed",
  "强势回调": "Strong PB",
  "加速↑": "A↑",
  "加速↓": "A↓",
  "加速": "A",
  "回调↑": "PB↑",
  "回调↓": "PB↓",
  "回调": "PB",
  "Accel↑": "A↑",
  "Accel↓": "A↓",
  "Accel": "A",
  "Pullback↑": "PB↑",
  "Pullback↓": "PB↓",
  "Pullback": "PB",
  "走弱": "Weak",
};

const HIDDEN_TAGS = new Set(["Core", "Strong PB", "Mixed", "核心强势", "强势回调", "不一致"]);

function pct(v) {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function perfScales(rows) {
  const keys = ["perf_w", "perf_m", "perf_q", "perf_h", "perf_y"];
  const scales = {};
  keys.forEach((key) => {
    const vals = rows.map((r) => Math.abs(Number(r[key]))).filter(Number.isFinite);
    scales[key] = Math.max(...vals, 0.01);
  });
  return scales;
}

function perfMicroBar(value, maxAbs) {
  const v = Number(value);
  if (!Number.isFinite(v)) {
    return '<span class="perf-cell"><span class="perf-val">—</span></span>';
  }
  const sign = v >= 0 ? "pos" : "neg";
  const scale = Math.max(Number(maxAbs) || 0.01, 0.01);
  const width = Math.min(100, Math.max(6, (Math.abs(v) / scale) * 100));
  return `<span class="perf-cell">
    <span class="perf-bar-wrap" aria-hidden="true"><span class="perf-bar ${sign}" style="width:${width.toFixed(1)}%"></span></span>
    <span class="perf-val ${sign}">${pct(v)}</span>
  </span>`;
}

function rankItemClass(rank) {
  if (rank <= 20) return "rank-hot";
  if (rank >= 100) return "rank-cold";
  return "rank-mid";
}

function rankCompactRow(row) {
  const items = [
    ["W", row.rank_w],
    ["M", row.rank_m],
    ["Q", row.rank_q],
    ["H", row.rank_h],
    ["Y", row.rank_y],
  ];
  return `<span class="rank-compact" aria-label="Rank W${row.rank_w} M${row.rank_m} Q${row.rank_q} H${row.rank_h} Y${row.rank_y}">${items
    .map(
      ([label, rank]) =>
        `<span class="rank-item ${rankItemClass(rank)}" title="${label} rank ${rank} — lower is stronger"><span class="rank-item-l">${label}</span><span class="rank-item-n">${rank}</span></span>`,
    )
    .join("")}</span>`;
}

function rankHeat(rank) {
  if (rank <= 20) return "rank-cell pos";
  if (rank >= 100) return "rank-cell neg";
  return "rank-cell";
}

function formatIndustryTags(tags) {
  return (tags || [])
    .filter((t) => !HIDDEN_TAGS.has(t))
    .map((t) => LEGACY_TAG_LABEL[t] || t);
}

function normalizeTrendLabel(text) {
  return LEGACY_TAG_LABEL[text] || text;
}

function buildTrendLabel(base, arrow) {
  return arrow ? `${base}${arrow}` : base;
}

function trendBadgeClass(text) {
  const t = normalizeTrendLabel(text);
  if (t === "A↑") return "trend-badge trend-accel-up";
  if (t === "A↓") return "trend-badge trend-accel-down";
  if (t === "PB↓") return "trend-badge trend-pullback-down";
  if (t === "PB↑") return "trend-badge trend-pullback-up";
  if (t === "A") return "trend-badge trend-accel-down";
  if (t === "PB") return "trend-badge trend-pullback-up";
  return "trend-badge";
}

function renderTrendBadge(text) {
  if (!text) return "—";
  const label = normalizeTrendLabel(text);
  return `<span class="${trendBadgeClass(label)}">${label}</span>`;
}

function computeShortTrend(row) {
  if (row.rank_m < row.rank_q) {
    if (row.rank_w < row.rank_m) return buildTrendLabel("A", "↑");
    if (row.rank_w > row.rank_m) return buildTrendLabel("A", "↓");
    return "A";
  }
  if (row.rank_m > row.rank_q) {
    if (row.rank_w < row.rank_m) return buildTrendLabel("PB", "↑");
    if (row.rank_w > row.rank_m) return buildTrendLabel("PB", "↓");
    return "PB";
  }
  return "";
}

function computeLongTrend(row) {
  if (row.rank_q < row.rank_h) {
    if (row.rank_m < row.rank_q) return buildTrendLabel("A", "↑");
    if (row.rank_m > row.rank_q) return buildTrendLabel("A", "↓");
    return "A";
  }
  if (row.rank_q > row.rank_h) {
    if (row.rank_m < row.rank_q) return buildTrendLabel("PB", "↑");
    if (row.rank_m > row.rank_q) return buildTrendLabel("PB", "↓");
    return "PB";
  }
  return "";
}

function getTopStrongIndustries(data) {
  return data.industries
    .filter((i) => i.is_top_strong && (i.stock_picks || []).length > 0)
    .sort((a, b) => b.score - a.score);
}

let currentTopListCount = 10;

function syncTopListLabels(count) {
  currentTopListCount = Number(count) || 10;
}

function rsUniverseCount(snapshot) {
  const meta = snapshot?.rs_meta || currentRsSnapshot?.rs_meta;
  if (meta) {
    const newStock =
      (meta.new_stock_m_count ?? 0) +
      (meta.new_stock_q_count ?? 0) +
      (meta.new_stock_h_count ?? 0) +
      (meta.new_stock_3q_count ?? 0);
    const main = Number(meta.computed_count ?? 0);
    if (main || newStock) return main + newStock;
  }
  const fallback = snapshot?.rs_count ?? currentRsSnapshot?.rows?.length;
  return fallback != null && fallback > 0 ? fallback : null;
}

function renderSummary(data, dashboard = null) {
  const top = getTopStrongIndustries(data);
  syncTopListLabels(data.top_strong_count ?? top.length);
  let dateText = data.snapshot_date || "—";
  const lag = Number(dashboard?.lag_days || 0);
  const target = dashboard?.target_date;
  if (lag > 0 && target && target !== data.snapshot_date) {
    dateText = `${dateText} (catch-up ${target})`;
  }
  const rsCount = rsUniverseCount(data) ?? dashboard?.summary?.rs_count;
  const rsText = rsCount != null ? rsCount.toLocaleString() : "—";
  document.getElementById("summary").innerHTML = `
    <p class="snapshot-meta" aria-label="Snapshot overview">
      As of ${dateText} · Top ${currentTopListCount}: ${top.length} · RS ${rsText}
    </p>
  `;
}

function watchlistIndustryLabel(row) {
  const map = new Map((currentSnapshot?.industries || []).map((i) => [i.industry_key, i.name]));
  return (row.industries || []).map((k) => map.get(k) || k).filter(Boolean).join(" · ");
}

function renderCandleSvg(bars) {
  const slice = (bars || []).filter(
    (b) => Number.isFinite(b.o) && Number.isFinite(b.h) && Number.isFinite(b.l) && Number.isFinite(b.c),
  );
  if (slice.length < 2) {
    return '<div class="watchlist-chart-placeholder">Chart unavailable</div>';
  }
  const W = 400;
  const H = 160;
  const PAD = 6;
  const lows = slice.map((b) => b.l);
  const highs = slice.map((b) => b.h);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const range = max - min || 1;
  const innerW = W - PAD * 2;
  const innerH = H - PAD * 2;
  const slot = innerW / slice.length;
  const y = (price) => PAD + ((max - price) / range) * innerH;
  const candles = slice
    .map((bar, i) => {
      const cx = PAD + i * slot + slot / 2;
      const bodyTop = y(Math.max(bar.o, bar.c));
      const bodyBot = y(Math.min(bar.o, bar.c));
      const bodyH = Math.max(bodyBot - bodyTop, 0.8);
      const up = bar.c >= bar.o;
      const color = up ? "#34d399" : "#f87171";
      const bodyW = Math.max(slot * 0.55, 1);
      return `<line x1="${cx}" y1="${y(bar.h)}" x2="${cx}" y2="${y(bar.l)}" stroke="${color}" stroke-width="1"></line>
        <rect x="${cx - bodyW / 2}" y="${bodyTop}" width="${bodyW}" height="${bodyH}" fill="${color}"></rect>`;
    })
    .join("");
  return `<svg class="watchlist-chart-img" viewBox="0 0 ${W} ${H}" role="img" aria-hidden="true">${candles}</svg>`;
}

function renderWatchlistCharts(payload) {
  const container = document.getElementById("watchlistChartGrid");
  if (!container) return;
  const rows = payload?.watchlist || [];
  if (!rows.length) {
    container.innerHTML = '<p class="hint">Charts appear after the daily watchlist is built.</p>';
    return;
  }
  container.innerHTML = rows
    .map((row) => {
      const symbol = row.symbol;
      const industry = watchlistIndustryLabel(row);
      const industryLine = industry
        ? `<p class="watchlist-chart-industry">${industry}</p>`
        : "";
      return `<article class="watchlist-chart-card">
        <a href="https://finviz.com/quote.ashx?t=${encodeURIComponent(symbol)}" target="_blank" rel="noreferrer">
          <header class="watchlist-chart-header">
            <span class="watchlist-chart-symbol">${symbol}</span>
            <span class="watchlist-chart-rs">RS ${Number(row.rs_score).toFixed(2)}</span>
          </header>
          ${industryLine}
          ${renderCandleSvg(row.chart_bars)}
        </a>
      </article>`;
    })
    .join("");
}

function renderCoreTable(data) {
  const tbody = document.querySelector("#coreTable tbody");
  const top = getTopStrongIndustries(data);
  const scales = perfScales(top);
  tbody.innerHTML = top
    .map((row) => {
      const shortTrend = computeShortTrend(row);
      const longTrend = computeLongTrend(row);
      return `<tr data-key="${row.industry_key}">
        <td><a class="industry-link" href="${row.finviz_url}" target="_blank" rel="noreferrer">${row.name}</a></td>
        <td class="num">${row.stocks}</td>
        <td class="num score-cell">${row.score.toFixed(3)}</td>
        <td>${perfMicroBar(row.perf_w, scales.perf_w)}</td>
        <td>${perfMicroBar(row.perf_m, scales.perf_m)}</td>
        <td>${perfMicroBar(row.perf_q, scales.perf_q)}</td>
        <td>${perfMicroBar(row.perf_h, scales.perf_h)}</td>
        <td>${perfMicroBar(row.perf_y, scales.perf_y)}</td>
        <td class="ranks-cell">${rankCompactRow(row)}</td>
        <td>${renderTrendBadge(shortTrend)}</td>
        <td>${renderTrendBadge(longTrend)}</td>
      </tr>`;
    })
    .join("");
}

function renderAllTable(data, filter = "") {
  const tbody = document.querySelector("#allTable tbody");
  const needle = filter.trim().toLowerCase();
  const rows = data.industries
    .filter((r) => !needle || r.name.toLowerCase().includes(needle))
    .sort((a, b) => b.score - a.score);

  tbody.innerHTML = rows
    .map((row) => {
      const status = row.excluded
        ? row.exclude_reason
        : row.is_top_strong
          ? `Top ${currentTopListCount}`
          : row.tier;
      return `<tr data-key="${row.industry_key}" class="${row.excluded ? "excluded" : ""}">
        <td>${row.name}</td>
        <td>${row.stocks}</td>
        <td>${row.excluded ? "—" : row.score.toFixed(3)}</td>
        <td class="${rankHeat(row.rank_w)}">${row.rank_w}</td>
        <td class="${rankHeat(row.rank_m)}">${row.rank_m}</td>
        <td class="${rankHeat(row.rank_q)}">${row.rank_q}</td>
        <td class="${rankHeat(row.rank_h)}">${row.rank_h}</td>
        <td class="${rankHeat(row.rank_y)}">${row.rank_y}</td>
        <td>${status}</td>
      </tr>`;
    })
    .join("");
}

function setButtonBusy(btn, busy, busyLabel) {
  if (!btn) return;
  if (busy) {
    if (!btn.dataset.defaultLabel) btn.dataset.defaultLabel = btn.textContent;
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    if (busyLabel) btn.textContent = busyLabel;
  } else {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    if (btn.dataset.defaultLabel) btn.textContent = btn.dataset.defaultLabel;
  }
}


async function loadDecisionView(date, snapshot = null) {
  const [snap, rsWatch] = await Promise.all([
    snapshot ? Promise.resolve(snapshot) : fetchJson(`/api/snapshots/${encodeURIComponent(date)}`),
    fetchJson(
      `/api/rs/${encodeURIComponent(date)}?watchlist_only=true&watchlist_limit=120`,
    ).catch(() => null),
  ]);
  currentSnapshot = snap;
  if (rsWatch?.rs_meta) {
    currentSnapshot = { ...snap, rs_meta: rsWatch.rs_meta };
  }
  renderSummary(currentSnapshot);
  renderCoreTable(snap);
  renderAllTable(snap);
  currentRsSnapshot = {
    snapshot_date: date,
    rows: [],
    watchlist: rsWatch?.watchlist || [],
    new_stock_leaderboard: [],
    rs_meta: rsWatch?.rs_meta || null,
  };
  renderWatchlistCharts(currentRsSnapshot);
  return snap;
}

async function loadSnapshot(date) {
  await loadDecisionView(date);
}

function applyAutoStatus(dashboard) {
  if (!dashboard) return;
  if (currentSnapshot) {
    renderSummary(currentSnapshot, dashboard);
  }
  const headline = dashboard.headline || "";
  const isError = dashboard.daily_status === "failed";
  const isRunning = dashboard.daily_status === "running";
  if (isRunning) {
    const progress = dashboard.progress || {};
    const label = progress.current_label ? ` · ${progress.current_label}` : "";
    setRsStatus(`${headline || "Updating…"}${label}`);
  } else if (headline) {
    setRsStatus(headline, isError);
  } else if (dashboard.daily_status === "ready" || dashboard.daily_status === "degraded") {
    setRsStatus("Data ready");
  }
}

async function watchAutomation() {
  if (autoRefreshBusy) return;
  autoRefreshBusy = true;
  try {
    const status = await fetchJson("/api/automation/status");
    applyAutoStatus(status);
    const displayDate = status.display_date;
    if (displayDate && displayDate !== currentSnapshot?.snapshot_date) {
      await loadSnapshot(displayDate);
    }
  } catch (err) {
    setRsStatus(`Status check failed: ${err.message}`, true);
  } finally {
    autoRefreshBusy = false;
  }
}

function startAutomationWatch() {
  if (automationTimer) clearInterval(automationTimer);
  automationTimer = setInterval(() => {
    watchAutomation().catch(() => {});
  }, 30000);
}

async function refreshFromServer() {
  const [snapshotResult, statusResult] = await Promise.allSettled([
    fetchJson("/api/snapshots/latest"),
    fetchJson("/api/automation/status"),
  ]);

  if (statusResult.status === "fulfilled") {
    applyAutoStatus(statusResult.value);
  }

  if (snapshotResult.status === "fulfilled") {
    const snapshot = snapshotResult.value;
    const date = snapshot.snapshot_date;
    await loadDecisionView(date, snapshot);
    if (statusResult.status === "fulfilled") {
      renderSummary(snapshot, statusResult.value);
    }
    return statusResult.status === "fulfilled" ? statusResult.value : null;
  }

  if (snapshotResult.status === "rejected") {
    showToast(snapshotResult.reason?.message || "Failed to load snapshot", true);
  }
  const status = statusResult.status === "fulfilled" ? statusResult.value : null;
  if (!status?.has_snapshot) {
    document.getElementById("summary").innerHTML =
      '<p class="snapshot-meta">No snapshot yet — first daily run in progress…</p>';
    setRsStatus("Waiting for first update");
  } else if (statusResult.status === "rejected") {
    setRsStatus("Cannot reach server status", true);
  }
  return status;
}

function setRsStatus(message, isError = false) {
  const el = document.getElementById("rsStatus");
  if (!el) return;
  el.textContent = message;
  el.className = isError ? "inline-status error" : "inline-status";
}

async function init() {
  renderHealthBadge("healthBadge").catch(() => {});
  document.getElementById("searchInput").addEventListener("input", (e) => {
    if (currentSnapshot) renderAllTable(currentSnapshot, e.target.value);
  });

  try {
    await refreshFromServer();
    startAutomationWatch();
  } catch (err) {
    showToast(err.message, true);
  }
}

init();
