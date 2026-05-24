let historyChart = null;
let currentSnapshot = null;
let selectedIndustryKey = null;
let currentRsSnapshot = null;

const rankColors = {
  rank_w: "#60a5fa",
  rank_m: "#34d399",
  rank_q: "#fbbf24",
  rank_h: "#f472b6",
  rank_y: "#a78bfa",
  score: "#f97316",
};

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

function pct(v) {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function rankHeat(rank) {
  if (rank <= 20) return "rank-cell pos";
  if (rank >= 100) return "rank-cell neg";
  return "rank-cell";
}

function formatIndustryTags(tags) {
  const hidden = new Set(["核心强势", "不一致", "强势回调"]);
  return (tags || []).filter((t) => !hidden.has(t));
}

function buildTrendLabel(base, arrow) {
  return arrow ? `${base}${arrow}` : base;
}

function trendBadgeClass(text) {
  if (text === "加速↑") return "trend-badge trend-accel-up";
  if (text === "加速↓") return "trend-badge trend-accel-down";
  if (text === "回调↓") return "trend-badge trend-pullback-down";
  if (text === "回调↑") return "trend-badge trend-pullback-up";
  if (text === "加速") return "trend-badge trend-accel-down";
  if (text === "回调") return "trend-badge trend-pullback-up";
  return "trend-badge";
}

function renderTrendBadge(text) {
  if (!text) return "—";
  return `<span class="${trendBadgeClass(text)}">${text}</span>`;
}

function computeShortTrend(row) {
  // 短期趋势：锚定3个月排名，月度优于3个月=加速；月度弱于3个月=回调。
  if (row.rank_m < row.rank_q) {
    if (row.rank_w < row.rank_m) return buildTrendLabel("加速", "↑");
    if (row.rank_w > row.rank_m) return buildTrendLabel("加速", "↓");
    return "加速";
  }
  if (row.rank_m > row.rank_q) {
    if (row.rank_w < row.rank_m) return buildTrendLabel("回调", "↑");
    if (row.rank_w > row.rank_m) return buildTrendLabel("回调", "↓");
    return "回调";
  }
  return "";
}

function computeLongTrend(row) {
  // 长期趋势：锚定6个月排名，季度优于6个月=加速；季度弱于6个月=回调。
  if (row.rank_q < row.rank_h) {
    if (row.rank_m < row.rank_q) return buildTrendLabel("加速", "↑");
    if (row.rank_m > row.rank_q) return buildTrendLabel("加速", "↓");
    return "加速";
  }
  if (row.rank_q > row.rank_h) {
    if (row.rank_m < row.rank_q) return buildTrendLabel("回调", "↑");
    if (row.rank_m > row.rank_q) return buildTrendLabel("回调", "↓");
    return "回调";
  }
  return "";
}

function getTopStrongIndustries(data) {
  return data.industries
    .filter((i) => i.is_top_strong)
    .sort((a, b) => b.score - a.score);
}

function renderSummary(data) {
  const top = getTopStrongIndustries(data);
  const active = data.industries.filter((i) => !i.excluded);
  document.getElementById("summary").innerHTML = `
    <div class="stat-card"><div class="value">${data.snapshot_date}</div><div class="label">快照日期</div></div>
    <div class="stat-card"><div class="value">${top.length}</div><div class="label">强势行业 Top 10</div></div>
    <div class="stat-card"><div class="value">${active.length}</div><div class="label">参与评分</div></div>
    <div class="stat-card"><div class="value">${top.reduce((n, i) => n + (i.stock_picks?.length || 0), 0)}</div><div class="label">筛选个股总数</div></div>
    <div class="stat-card"><div class="value">${data.rs_count ?? 0}</div><div class="label">RS样本数</div></div>
    <div class="stat-card"><div class="value">${data.rs_watchlist_count ?? 0}</div><div class="label">交叉观察名单</div></div>
  `;
}

function renderRsTable(payload) {
  const tbody = document.querySelector("#rsTable tbody");
  if (!tbody) return;
  const rows = payload?.rows || [];
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="hint">该日期暂无 RS 数据，请点击“刷新个股RS”</td></tr>';
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
    tbody.innerHTML = '<tr><td colspan="4" class="hint">暂无交叉观察名单（需先生成 RS 且 Top10 个股已抓取）</td></tr>';
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
    container.innerHTML = '<p class="hint">暂无观察名单图表（需先生成 RS 交叉名单）。</p>';
    return;
  }
  container.innerHTML = rows
    .map((row) => {
      const symbol = row.symbol;
      return `<article class="watchlist-chart-card">
        <a href="https://finviz.com/quote.ashx?t=${encodeURIComponent(symbol)}" target="_blank" rel="noreferrer">
          <img class="watchlist-chart-img" src="${finvizDailyChartUrl(symbol)}" alt="${symbol} 日K图" loading="lazy" />
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
    target.innerHTML = '<span class="hint">覆盖率：暂无（请先刷新个股RS）</span>';
    return;
  }
  const ratio = (Number(meta.coverage_ratio || 0) * 100).toFixed(1);
  target.innerHTML = `
    <span class="coverage-item">股票池 ${meta.universe_count}</span>
    <span class="coverage-item">RS有效 ${meta.computed_count}</span>
    <span class="coverage-item">覆盖率 ${ratio}%</span>
    <span class="coverage-item">数据不足 ${meta.insufficient_history_count}</span>
    <span class="coverage-item">无数据 ${meta.no_bars_count}</span>
  `;
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
    return `<span class="hint">无匹配 ${link}</span>`;
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
      ? `<a class="industry-link" href="${row.stock_screener_url}" target="_blank" rel="noreferrer">在 Finviz 查看</a>`
      : '';
    return `<p class="hint">无匹配 ${link}</p>`;
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
            <span class="strong-card-hits">${(row.stock_picks || []).length} 只股票</span>
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
  tbody.innerHTML = top
    .map((row) => {
      const shortTrend = computeShortTrend(row);
      const longTrend = computeLongTrend(row);
      return `<tr data-key="${row.industry_key}">
        <td><a class="industry-link" href="${row.finviz_url}" target="_blank" rel="noreferrer">${row.name}</a></td>
        <td>${row.stocks}</td>
        <td>${row.score.toFixed(3)}</td>
        <td class="${row.perf_w >= 0 ? "pos" : "neg"}">${pct(row.perf_w)}</td>
        <td class="${row.perf_m >= 0 ? "pos" : "neg"}">${pct(row.perf_m)}</td>
        <td class="${row.perf_q >= 0 ? "pos" : "neg"}">${pct(row.perf_q)}</td>
        <td class="${row.perf_h >= 0 ? "pos" : "neg"}">${pct(row.perf_h)}</td>
        <td class="${row.perf_y >= 0 ? "pos" : "neg"}">${pct(row.perf_y)}</td>
        <td>${row.rank_w}/${row.rank_m}/${row.rank_q}/${row.rank_h}/${row.rank_y}</td>
        <td>${renderTrendBadge(shortTrend)}</td>
        <td>${renderTrendBadge(longTrend)}</td>
      </tr>`;
    })
    .join("");
  bindIndustryRowClicks(tbody);
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
          ? "Top 10"
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
  bindIndustryRowClicks(tbody);
}

function bindIndustryRowClicks(tbody) {
  tbody.querySelectorAll("tr[data-key]").forEach((tr) => {
    tr.addEventListener("click", () => {
      const key = tr.dataset.key;
      selectedIndustryKey = key;
      document.getElementById("industrySelect").value = key;
      loadHistoryChart();
    });
  });
}

function populateIndustrySelect(data) {
  const select = document.getElementById("industrySelect");
  const options = data.industries
    .filter((i) => !i.excluded)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(
      (i) => `<option value="${i.industry_key}">${i.name}</option>`
    )
    .join("");
  select.innerHTML = options;
  if (!selectedIndustryKey && data.industries.length) {
    const firstCore = getTopStrongIndustries(data)[0];
    selectedIndustryKey = (firstCore || data.industries[0]).industry_key;
  }
  select.value = selectedIndustryKey;
}

async function loadDates() {
  const dates = await fetchJson("/api/snapshots/dates");
  const select = document.getElementById("dateSelect");
  select.innerHTML = dates.map((d) => `<option value="${d}">${d}</option>`).join("");
  if (dates.length) {
    select.value = dates[0];
  }
  return dates;
}

async function loadSnapshot(date) {
  currentSnapshot = await fetchJson(`/api/snapshots/${date}`);
  renderSummary(currentSnapshot);
  renderCoreTable(currentSnapshot);
  renderAllTable(currentSnapshot);
  renderStrongCards(currentSnapshot);
  await loadRsSnapshot(date);
  renderCoveragePanel(currentSnapshot, currentRsSnapshot);
  populateIndustrySelect(currentSnapshot);
  await loadHistoryChart();
}

async function loadRsSnapshot(date) {
  try {
    currentRsSnapshot = await fetchJson(`/api/rs/${encodeURIComponent(date)}?limit=120&watchlist_limit=120`);
  } catch (err) {
    currentRsSnapshot = { snapshot_date: date, rows: [], watchlist: [] };
  }
  renderRsTable(currentRsSnapshot);
  renderWatchlistTable(currentRsSnapshot);
  renderWatchlistCharts(currentRsSnapshot);
}

function destroyChart() {
  if (historyChart) {
    historyChart.destroy();
    historyChart = null;
  }
}

async function loadHistoryChart() {
  const key = document.getElementById("industrySelect").value || selectedIndustryKey;
  if (!key) return;

  const multi = document.getElementById("multiRankToggle").checked;
  destroyChart();

  const ctx = document.getElementById("historyChart");

  if (multi) {
    const payload = await fetchJson(
      `/api/industry/${key}/history/multi?metrics=rank_w,rank_m,rank_q,rank_h,rank_y`
    );
    const dates = payload.series.rank_m?.map((p) => p.date) || [];
    historyChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: dates,
        datasets: Object.entries(payload.series).map(([metric, points]) => ({
          label: metric,
          data: points.map((p) => p.value),
          borderColor: rankColors[metric] || "#fff",
          tension: 0.2,
          pointRadius: 2,
        })),
      },
      options: chartOptions(true),
    });
    return;
  }

  const metric = document.getElementById("metricSelect").value;
  const payload = await fetchJson(`/api/industry/${key}/history?metric=${metric}`);
  const labels = payload.series.map((p) => p.snapshot_date);
  const values = payload.series.map((p) => p.value);

  historyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: `${payload.series[0]?.name || key} · ${metric}`,
          data: values,
          borderColor: rankColors[metric] || "#3b82f6",
          tension: 0.2,
          pointRadius: 3,
          fill: false,
        },
      ],
    },
    options: chartOptions(metric.startsWith("rank_")),
  });
}

function chartOptions(invertY) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: "#e7ecf3" } },
    },
    scales: {
      x: { ticks: { color: "#93a4b8" }, grid: { color: "rgba(255,255,255,0.06)" } },
      y: {
        reverse: invertY,
        ticks: { color: "#93a4b8" },
        grid: { color: "rgba(255,255,255,0.06)" },
        title: {
          display: invertY,
          text: "排名（越小越强，曲线向下=走强）",
          color: "#93a4b8",
        },
      },
    },
  };
}

function setConfigStatus(message, isError = false) {
  const el = document.getElementById("configStatus");
  el.textContent = message;
  el.className = isError ? "config-status error" : "config-status";
}

function setRsStatus(message, isError = false) {
  const el = document.getElementById("rsStatus");
  if (!el) return;
  el.textContent = message;
  el.className = isError ? "inline-status error" : "inline-status";
}

function updateWeightHint(weights, normalized) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const parts = Object.entries(normalized || {})
    .map(([k, v]) => `${k}: ${(v * 100).toFixed(1)}%`)
    .join(" · ");
  document.getElementById("weightHint").textContent =
    `当前权重总和 ${total.toFixed(2)}，归一化后 → ${parts}`;
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
  document.getElementById("topListCount").value = t.top_list_count ?? 10;
  document.getElementById("accelerationRankDelta").value = t.acceleration_rank_delta ?? 5;
  document.getElementById("pullbackMidtermRankMax").value = t.pullback_midterm_rank_max ?? 30;
  document.getElementById("pullbackWeekRankMin").value = t.pullback_week_rank_min ?? 40;

  const sf = cfg.stock_filters || {};
  document.getElementById("stockPriceAboveSma20").value = sf.price_above_sma20 ?? "ta_sma20_pa";
  document.getElementById("stockSma20AboveSma50").value = sf.sma20_above_sma50 ?? "ta_sma50_sb20";
  document.getElementById("stockDollarVolumeMin").value = sf.dollar_volume_min ?? "sh_curvol_ousd100000";

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
  setConfigStatus(`已套用“${name === "conservative" ? "保守" : name === "balanced" ? "均衡" : "激进"}”预设，点击保存即可生效`);
}

async function loadConfigForm() {
  const cfg = await fetchJson("/api/config");
  fillConfigForm(cfg);
  return cfg;
}

async function saveConfig(recompute = false) {
  const payload = readConfigForm();
  setConfigStatus("保存中…");
  const result = await fetchJson("/api/config", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  fillConfigForm(result.config);

  if (recompute) {
    setConfigStatus("配置已保存，正在重新计算快照…");
    const date = document.getElementById("dateSelect").value;
    const query = date ? `?snapshot_date=${encodeURIComponent(date)}` : "";
    await fetchJson(`/api/snapshots/recompute-latest${query}`, { method: "POST" });
    await loadSnapshot(date || (await loadDates())[0]);
    setConfigStatus("配置已保存，当前快照已按新规则重算");
  } else {
    setConfigStatus("配置已保存");
  }
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
    saveConfig(false).catch((err) => setConfigStatus(err.message, true));
  });

  document.getElementById("saveAndRecomputeBtn").addEventListener("click", () => {
    saveConfig(true).catch((err) => setConfigStatus(err.message, true));
  });
}

async function fetchCoreStocks() {
  const date = document.getElementById("dateSelect").value;
  if (!date) return;
  const btn = document.getElementById("fetchCoreStocksBtn");
  btn.disabled = true;
  btn.textContent = "抓取中…";
  try {
    await fetchJson(`/api/snapshots/${encodeURIComponent(date)}/fetch-stocks`, {
      method: "POST",
    });
    await loadSnapshot(date);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "刷新 Top 10 个股";
  }
}

async function computeRs() {
  const date = document.getElementById("dateSelect").value;
  if (!date) return;
  const btn = document.getElementById("computeRsBtn");
  const startAt = Date.now();
  btn.disabled = true;
  btn.textContent = "计算中…";
  setRsStatus("已开始计算，首次全量可能需要几分钟…");
  let timer = null;

  const pollProgress = async () => {
    const p = await fetchJson(`/api/snapshots/${encodeURIComponent(date)}/rs-progress`);
    if (p.status === "running" && p.total > 0) {
      const pct = ((p.progress_ratio || 0) * 100).toFixed(1);
      setRsStatus(`RS计算中：${p.processed}/${p.total} (${pct}%)`);
    }
  };

  try {
    await pollProgress().catch(() => {});
    timer = setInterval(() => {
      pollProgress().catch(() => {});
    }, 2000);
    await fetchJson(`/api/snapshots/${encodeURIComponent(date)}/compute-rs`, {
      method: "POST",
    });
    await loadSnapshot(date);
    const sec = ((Date.now() - startAt) / 1000).toFixed(1);
    setRsStatus(`计算完成，耗时 ${sec}s`);
  } catch (err) {
    setRsStatus(`计算失败：${err.message}`, true);
    alert(err.message);
  } finally {
    if (timer) clearInterval(timer);
    btn.disabled = false;
    btn.textContent = "刷新个股RS";
  }
}

async function init() {
  document.getElementById("refreshBtn").addEventListener("click", () => location.reload());
  document.getElementById("dateSelect").addEventListener("change", (e) => {
    loadSnapshot(e.target.value).catch(alert);
  });
  document.getElementById("industrySelect").addEventListener("change", (e) => {
    selectedIndustryKey = e.target.value;
    loadHistoryChart().catch(alert);
  });
  document.getElementById("metricSelect").addEventListener("change", () => {
    if (!document.getElementById("multiRankToggle").checked) {
      loadHistoryChart().catch(alert);
    }
  });
  document.getElementById("multiRankToggle").addEventListener("change", () => {
    loadHistoryChart().catch(alert);
  });
  document.getElementById("searchInput").addEventListener("input", (e) => {
    if (currentSnapshot) renderAllTable(currentSnapshot, e.target.value);
  });
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyThresholdPreset(btn.dataset.preset));
  });

  bindConfigForm();
  document.getElementById("fetchCoreStocksBtn").addEventListener("click", () => {
    fetchCoreStocks().catch(alert);
  });
  document.getElementById("computeRsBtn").addEventListener("click", () => {
    computeRs().catch(alert);
  });

  try {
    await loadConfigForm();
    const dates = await loadDates();
    if (!dates.length) {
      document.getElementById("summary").innerHTML =
        '<p class="hint">尚无历史快照。请在项目目录运行：<code>python run_daily.py</code></p>';
      return;
    }
    await loadSnapshot(dates[0]);
  } catch (err) {
    alert(err.message);
  }
}

init();
