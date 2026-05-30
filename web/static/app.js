let currentSnapshot = null;
let currentRsSnapshot = null;
let autoRefreshBusy = false;
let automationTimer = null;

const NEW_STOCK_COHORT_LABEL = { M: "Monthly", Q: "Quarter", H: "Half", "3Q": "3Q" };

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

const thresholdPresets = {
  conservative: {
    tier_a_score: 0.85,
    tier_b_score: 0.72,
    core_rank_max: 20,
    max_rank_spread: 45,
    top_list_count: 8,
    acceleration_rank_delta: 8,
    pullback_midterm_rank_max: 22,
    pullback_week_rank_min: 55,
  },
  balanced: {
    tier_a_score: 0.8,
    tier_b_score: 0.66,
    core_rank_max: 25,
    max_rank_spread: 55,
    top_list_count: 10,
    acceleration_rank_delta: 6,
    pullback_midterm_rank_max: 28,
    pullback_week_rank_min: 45,
  },
  aggressive: {
    tier_a_score: 0.74,
    tier_b_score: 0.6,
    core_rank_max: 35,
    max_rank_spread: 70,
    top_list_count: 12,
    acceleration_rank_delta: 4,
    pullback_midterm_rank_max: 35,
    pullback_week_rank_min: 35,
  },
};

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
    .filter((i) => i.is_top_strong)
    .sort((a, b) => b.score - a.score);
}

let currentTopListCount = 15;

function syncTopListLabels(count) {
  currentTopListCount = Number(count) || 15;
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

function renderRsTable(payload) {
  const tbody = document.querySelector("#rsTable tbody");
  if (!tbody) return;
  const rows = payload?.rows || [];
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="hint">No RS data yet — fills in after the daily run.</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map(
      (row) => `<tr>
        <td><a class="industry-link" href="https://finviz.com/quote.ashx?t=${encodeURIComponent(row.symbol)}" target="_blank" rel="noreferrer">${row.symbol}</a></td>
        <td>${row.rs_score.toFixed(3)}</td>
        <td>${row.tier}</td>
        <td class="${row.perf_w >= 0 ? "pos" : "neg"}">${pct(row.perf_w)}</td>
        <td class="${row.perf_m >= 0 ? "pos" : "neg"}">${pct(row.perf_m)}</td>
        <td class="${row.perf_q >= 0 ? "pos" : "neg"}">${pct(row.perf_q)}</td>
        <td class="${row.perf_h >= 0 ? "pos" : "neg"}">${pct(row.perf_h)}</td>
        <td class="${row.perf_y >= 0 ? "pos" : "neg"}">${pct(row.perf_y)}</td>
        <td>${row.rank_w}/${row.rank_m}/${row.rank_q}/${row.rank_h}/${row.rank_y}</td>
      </tr>`
    )
    .join("");
}

function renderWatchlistTable(payload) {
  const tbody = document.querySelector("#watchlistTable tbody");
  if (!tbody) return;
  const industryNameMap = new Map(
    ((currentSnapshot?.industries || []).map((i) => [i.industry_key, i.name]))
  );
  const rows = payload?.watchlist || [];
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="hint">No watchlist yet — built after daily cross-screen.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (row) => `<tr>
        <td><a class="industry-link" href="https://finviz.com/quote.ashx?t=${encodeURIComponent(row.symbol)}" target="_blank" rel="noreferrer">${row.symbol}</a></td>
        <td>${row.rs_rank}</td>
        <td>${row.rs_score.toFixed(3)}</td>
        <td>${(row.industries || []).map((k) => industryNameMap.get(k) || k).join(" / ")}</td>
      </tr>`
    )
    .join("");
}

function finvizDailyChartUrl(symbol) {
  return `https://charts2.finviz.com/chart.ashx?t=${encodeURIComponent(symbol)}&ty=c&ta=1&p=d&s=l&theme=dark`;
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
      return `<article class="watchlist-chart-card">
        <a href="https://finviz.com/quote.ashx?t=${encodeURIComponent(symbol)}" target="_blank" rel="noreferrer">
          <img class="watchlist-chart-img" src="${finvizDailyChartUrl(symbol)}" alt="${symbol} daily chart" loading="lazy" />
        </a>
      </article>`;
    })
    .join("");
}

function renderCoveragePanel(snapshot, rsPayload) {
  const target = document.getElementById("coveragePanel");
  if (!target) return;
  const meta = snapshot?.rs_meta || rsPayload?.rs_meta;
  if (!meta) {
    target.innerHTML = '<span class="hint">Coverage: waiting on RS run</span>';
    return;
  }
  const newStockRsCount =
    (meta.new_stock_m_count ?? 0) +
    (meta.new_stock_q_count ?? 0) +
    (meta.new_stock_h_count ?? 0) +
    (meta.new_stock_3q_count ?? 0);
  const covered = (meta.computed_count ?? 0) + newStockRsCount;
  target.innerHTML = `
    <span class="coverage-item">Universe ${meta.universe_count}</span>
    <span class="coverage-item">Covered ${covered}</span>
    <span class="coverage-item">Main RS ${meta.computed_count}</span>
    <span class="coverage-item">New IPO RS ${newStockRsCount}</span>
    <span class="coverage-item">New list ${meta.new_stock_leaderboard_count ?? 0}</span>
    <span class="coverage-item">No bars ${meta.no_bars_count}</span>
  `;
}

function fmtPerf(v) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  return `${Number(v).toFixed(1)}%`;
}

function renderNewStockLeaderboard(payload) {
  const tbody = document.querySelector("#newStockTable tbody");
  if (!tbody) return;
  const rows = payload?.new_stock_leaderboard || [];
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="hint">No new-issue RS leaderboard yet</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map((row) => {
      const cohort = NEW_STOCK_COHORT_LABEL[row.cohort] || row.cohort;
      return `<tr>
        <td>${cohort}</td>
        <td><a class="industry-link" href="https://finviz.com/quote.ashx?t=${encodeURIComponent(row.symbol)}" target="_blank" rel="noreferrer">${row.symbol}</a></td>
        <td>${row.bar_count ?? "—"}</td>
        <td>${row.rs_score.toFixed(3)}</td>
        <td>${row.tier}</td>
        <td class="${Number(row.perf_w) >= 0 ? "pos" : "neg"}">${fmtPerf(row.perf_w)}</td>
        <td class="${Number(row.perf_m) >= 0 ? "pos" : "neg"}">${fmtPerf(row.perf_m)}</td>
        <td class="${Number(row.perf_q) >= 0 ? "pos" : "neg"}">${fmtPerf(row.perf_q)}</td>
        <td class="${Number(row.perf_h) >= 0 ? "pos" : "neg"}">${fmtPerf(row.perf_h)}</td>
        <td class="${Number(row.perf_tq) >= 0 ? "pos" : "neg"}">${fmtPerf(row.perf_tq)}</td>
      </tr>`;
    })
    .join("");
}

function renderStockPicks(row) {
  if (row.stock_picks_error) {
    return `<span class="hint error-text">${row.stock_picks_error}</span>`;
  }
  const tickers = row.stock_picks || [];
  if (!tickers.length) {
    const link = row.stock_screener_url
      ? `<a class="industry-link" href="${row.stock_screener_url}" target="_blank" rel="noreferrer">Finviz</a>`
      : "—";
    return `<span class="hint">No hits ${link}</span>`;
  }
  return tickers
    .map(
      (t) =>
        `<a class="ticker-chip" href="https://finviz.com/quote.ashx?t=${encodeURIComponent(t)}" target="_blank" rel="noreferrer">${t}</a>`
    )
    .join("");
}


function renderTickerList(row) {
  const tickers = row.stock_picks || [];
  if (row.stock_picks_error) {
    return `<p class="hint error-text">${row.stock_picks_error}</p>`;
  }
  if (!tickers.length) {
    const link = row.stock_screener_url
      ? `<a class="industry-link" href="${row.stock_screener_url}" target="_blank" rel="noreferrer">Open in Finviz</a>`
      : '';
    return `<p class="hint">No hits ${link}</p>`;
  }
  return `<ul class="ticker-list">${tickers
    .map(
      (t) =>
        `<li><a class="ticker-chip" href="https://finviz.com/quote.ashx?t=${encodeURIComponent(t)}" target="_blank" rel="noreferrer">${t}</a></li>`
    )
    .join('')}</ul>`;
}

function renderStrongCards(data) {
  const container = document.getElementById('strongIndustryCards');
  if (!container) return;
  const top = getTopStrongIndustries(data);
  container.innerHTML = top
    .map(
      (row, idx) => `
      <article class="strong-card" data-key="${row.industry_key}">
        <header class="strong-card-header">
          <div class="strong-card-title-wrap">
            <span class="strong-card-rank">#${idx + 1}</span>
            <a class="industry-link strong-card-title" href="${row.finviz_url}" target="_blank" rel="noreferrer">${row.name}</a>
          </div>
          <div class="strong-card-right">
            <span class="strong-card-hits">${(row.stock_picks || []).length} names</span>
            <span class="strong-card-meta">Score ${row.score.toFixed(3)}</span>
          </div>
        </header>
        ${renderTickerList(row)}
      </article>`
    )
    .join('');
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

function enhanceHelpTips() {
  document.querySelectorAll(".help-tip[data-tip]").forEach((el) => {
    el.setAttribute("tabindex", "0");
    el.setAttribute("role", "button");
    if (!el.getAttribute("aria-label")) {
      el.setAttribute("aria-label", el.getAttribute("data-tip") || "Help");
    }
  });
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
  renderSummary(snap);
  renderCoreTable(snap);
  renderAllTable(snap);
  renderStrongCards(snap);
  if (rsWatch) {
    currentRsSnapshot = {
      snapshot_date: date,
      rows: [],
      watchlist: rsWatch.watchlist || [],
      new_stock_leaderboard: [],
      rs_meta: rsWatch.rs_meta || null,
    };
    renderWatchlistCharts(currentRsSnapshot);
  }
  return snap;
}

async function loadSnapshot(date, { includeRsDetails = true } = {}) {
  await loadDecisionView(date);
  if (includeRsDetails) {
    loadRsDetails(date).catch(() => {});
  }
}

async function loadRsDetails(date) {
  if (currentRsSnapshot?.rows?.length) {
    renderCoveragePanel(currentSnapshot, currentRsSnapshot);
    return;
  }
  await loadRsSnapshot(date);
  renderCoveragePanel(currentSnapshot, currentRsSnapshot);
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
    loadRsDetails(date).catch(() => {});
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

async function loadRsSnapshot(date) {
  try {
    currentRsSnapshot = await fetchJson(`/api/rs/${encodeURIComponent(date)}?limit=120&watchlist_limit=120`);
  } catch (err) {
    currentRsSnapshot = {
      snapshot_date: date,
      rows: [],
      watchlist: [],
      new_stock_leaderboard: [],
    };
  }
  renderRsTable(currentRsSnapshot);
  renderNewStockLeaderboard(currentRsSnapshot);
  renderWatchlistTable(currentRsSnapshot);
  renderWatchlistCharts(currentRsSnapshot);
  if (currentSnapshot) renderSummary(currentSnapshot);
}

function setRsStatus(message, isError = false) {
  const el = document.getElementById("rsStatus");
  if (!el) return;
  el.textContent = message;
  el.className = isError ? "inline-status error" : "inline-status";
}

function setConfigStatus(message, isError = false) {
  const el = document.getElementById("configStatus");
  el.textContent = message;
  el.className = isError ? "config-status error" : "config-status";
}

function updateWeightHint(weights, normalized) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const parts = Object.entries(normalized || {})
    .map(([k, v]) => `${k}: ${(v * 100).toFixed(1)}%`)
    .join(" · ");
  document.getElementById("weightHint").textContent =
    `Weight sum ${total.toFixed(2)} · normalized → ${parts}`;
}

function fillConfigForm(cfg) {
  const w = cfg.weights || {};
  document.getElementById("weightWeek").value = w.week ?? 0.1;
  document.getElementById("weightMonth").value = w.month ?? 0.25;
  document.getElementById("weightQuarter").value = w.quarter ?? 0.25;
  document.getElementById("weightHalf").value = w.half ?? 0.25;
  document.getElementById("weightYear").value = w.year ?? 0.15;

  const t = cfg.thresholds || {};
  document.getElementById("tierAScore").value = t.tier_a_score ?? 0.8;
  document.getElementById("tierBScore").value = t.tier_b_score ?? 0.65;
  document.getElementById("coreRankMax").value = t.core_rank_max ?? 25;
  document.getElementById("maxRankSpread").value = t.max_rank_spread ?? 60;
  document.getElementById("topListCount").value = t.top_list_count ?? 15;
  syncTopListLabels(t.top_list_count ?? 15);
  document.getElementById("accelerationRankDelta").value = t.acceleration_rank_delta ?? 5;
  document.getElementById("pullbackMidtermRankMax").value = t.pullback_midterm_rank_max ?? 30;
  document.getElementById("pullbackWeekRankMin").value = t.pullback_week_rank_min ?? 40;

  const sf = cfg.stock_filters || {};
  document.getElementById("stockPriceAboveSma20").value = sf.price_above_sma20 ?? "ta_sma20_pa";
  document.getElementById("stockSma20AboveSma50").value = sf.sma20_above_sma50 ?? "ta_sma50_sb20";
  document.getElementById("stockDollarVolumeMin").value = sf.dollar_volume_min ?? "sh_curvol_ousd100000";
  document.getElementById("stockEpsGrowthQoq").value = sf.eps_growth_qoq_min ?? "fa_epsqoq_o10";
  document.getElementById("stockSalesGrowthQoq").value = sf.sales_growth_qoq_min ?? "fa_salesqoq_o10";

  const rs = cfg.stock_rs || {};
  document.getElementById("rsTimeoutSeconds").value = rs.request_timeout_seconds ?? 20;
  document.getElementById("rsMinPriceRows").value = rs.min_price_rows ?? 260;
  document.getElementById("rsTierAScore").value = rs.tier_a_score ?? 0.8;
  document.getElementById("rsTierBScore").value = rs.tier_b_score ?? 0.65;
  document.getElementById("rsCrossTopPercent").value = rs.cross_top_percent ?? 0.1;
  document.getElementById("rsUniverseCap").value = rs.universe_cap ?? 0;
  document.getElementById("rsPreferStooq").checked = Boolean(rs.prefer_stooq);

  updateWeightHint(w, cfg.weights_normalized);
}

function readConfigForm() {
  return {
    weights: {
      week: parseFloat(document.getElementById("weightWeek").value),
      month: parseFloat(document.getElementById("weightMonth").value),
      quarter: parseFloat(document.getElementById("weightQuarter").value),
      half: parseFloat(document.getElementById("weightHalf").value),
      year: parseFloat(document.getElementById("weightYear").value),
    },
    thresholds: {
      tier_a_score: parseFloat(document.getElementById("tierAScore").value),
      tier_b_score: parseFloat(document.getElementById("tierBScore").value),
      core_rank_max: parseInt(document.getElementById("coreRankMax").value, 10),
      max_rank_spread: parseInt(document.getElementById("maxRankSpread").value, 10),
      top_list_count: parseInt(document.getElementById("topListCount").value, 10),
      acceleration_rank_delta: parseInt(
        document.getElementById("accelerationRankDelta").value,
        10
      ),
      pullback_midterm_rank_max: parseInt(
        document.getElementById("pullbackMidtermRankMax").value,
        10
      ),
      pullback_week_rank_min: parseInt(
        document.getElementById("pullbackWeekRankMin").value,
        10
      ),
    },
    stock_filters: {
      price_above_sma20: document.getElementById("stockPriceAboveSma20").value.trim(),
      sma20_above_sma50: document.getElementById("stockSma20AboveSma50").value.trim(),
      dollar_volume_min: document.getElementById("stockDollarVolumeMin").value.trim(),
      eps_growth_qoq_min: document.getElementById("stockEpsGrowthQoq").value.trim(),
      sales_growth_qoq_min: document.getElementById("stockSalesGrowthQoq").value.trim(),
    },
    stock_rs: {
      request_timeout_seconds: parseInt(document.getElementById("rsTimeoutSeconds").value, 10),
      min_price_rows: parseInt(document.getElementById("rsMinPriceRows").value, 10),
      tier_a_score: parseFloat(document.getElementById("rsTierAScore").value),
      tier_b_score: parseFloat(document.getElementById("rsTierBScore").value),
      cross_top_percent: parseFloat(document.getElementById("rsCrossTopPercent").value),
      universe_cap: parseInt(document.getElementById("rsUniverseCap").value, 10),
      prefer_stooq: document.getElementById("rsPreferStooq").checked,
    },
  };
}

function applyThresholdPreset(name) {
  const preset = thresholdPresets[name];
  if (!preset) return;

  document.getElementById("tierAScore").value = preset.tier_a_score;
  document.getElementById("tierBScore").value = preset.tier_b_score;
  document.getElementById("coreRankMax").value = preset.core_rank_max;
  document.getElementById("maxRankSpread").value = preset.max_rank_spread;
  document.getElementById("topListCount").value = preset.top_list_count;
  document.getElementById("accelerationRankDelta").value = preset.acceleration_rank_delta;
  document.getElementById("pullbackMidtermRankMax").value = preset.pullback_midterm_rank_max;
  document.getElementById("pullbackWeekRankMin").value = preset.pullback_week_rank_min;
  const presetName =
    name === "conservative" ? "Conservative" : name === "balanced" ? "Balanced" : "Aggressive";
  setConfigStatus(`Applied ${presetName} preset — click Save to keep`);
}

async function loadConfigForm() {
  const cfg = await fetchJson("/api/config");
  fillConfigForm(cfg);
  return cfg;
}

async function saveConfig() {
  const payload = readConfigForm();
  setConfigStatus("Saving…");
  const result = await fetchJson("/api/config", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  fillConfigForm(result.config);
  setConfigStatus("Saved — applies on next daily run");
}

function bindConfigForm() {
  const weightIds = ["weightWeek", "weightMonth", "weightQuarter", "weightHalf", "weightYear"];
  weightIds.forEach((id) => {
    document.getElementById(id).addEventListener("input", () => {
      const payload = readConfigForm();
      const total = Object.values(payload.weights).reduce((a, b) => a + b, 0);
      const normalized = Object.fromEntries(
        Object.entries(payload.weights).map(([k, v]) => [k, total > 0 ? v / total : 0])
      );
      updateWeightHint(payload.weights, normalized);
    });
  });

  document.getElementById("configForm").addEventListener("submit", (e) => {
    e.preventDefault();
    saveConfig().catch((err) => setConfigStatus(err.message, true));
  });
}

async function init() {
  enhanceHelpTips();
  renderHealthBadge("healthBadge").catch(() => {});
  document.getElementById("searchInput").addEventListener("input", (e) => {
    if (currentSnapshot) renderAllTable(currentSnapshot, e.target.value);
  });
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyThresholdPreset(btn.dataset.preset));
  });

  bindConfigForm();

  try {
    await refreshFromServer();
    startAutomationWatch();
    loadConfigForm().catch(() => {});
  } catch (err) {
    showToast(err.message, true);
  }
}

init();
