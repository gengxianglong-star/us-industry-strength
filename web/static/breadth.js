let chartInstances = [];
let chartByCanvas = {};
let currentChartDays = 365;
let latestPayload = null;
let syncPollingTimer = null;
let ratioBg = null;
let activeCockpitKey = null;
let cockpitClickBound = false;
const BREADTH_MORNING_SYNC_HOUR_BJ = 6;

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
  el.textContent = message;
  el.style.background = isError ? "rgba(153,27,27,0.95)" : "rgba(30,58,138,0.95)";
  el.style.color = "#fff";
  clearTimeout(el._timer);
  el._timer = setTimeout(() => {
    if (el) el.textContent = "";
  }, 4200);
}

/** 驾驶舱卡片 → 图表 canvas 与要高亮的序列 */
const COCKPIT_CHART_LINK = {
  quarter_trend: { canvasId: "quarter25Chart", datasets: ["Up 25% Quarter", "Down 25% Quarter"] },
  half_season_trend: { canvasId: "spxBreadthChart", datasets: ["Up 13%/34D", "Down 13%/34D"] },
  monthly_trend: { canvasId: "month25Chart", datasets: ["Up 25% Month", "Down 25% Month"] },
  cross_5_10: { canvasId: "ratioChart", datasets: ["5 Day Ratio", "10 Day Ratio"] },
  trend_10d: { canvasId: "ratioChart", datasets: ["10 Day Ratio"] },
  trend_5d: { canvasId: "ratioChart", datasets: ["5 Day Ratio"] },
  extreme_alert: { canvasId: "ratioChart", datasets: ["T2108"] },
};

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

function clampPos(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 50;
  return Math.max(0, Math.min(100, n));
}

/** 翠绿阶梯：基准=四模块绿灯；[1.0,1.5) 与 (1.5,2.0] 各 5 档 */
const GREEN_BASELINE_BG = "#1b5e3a";
const GREEN_LIGHTER_BG = ["#236848", "#297a50", "#2d7856", "#388a66", "#459c76"];
const GREEN_DARKER_BG = ["#155434", "#134e30", "#104a2e", "#0c4026", "#08361e"];
/** 玫红阶梯：基准=四模块红灯；[0.5,0.75) 与 (0.75,1.0] 各 5 档 */
const RED_BASELINE_BG = "#5e343c";
const RED_LIGHTER_BG = ["#6c3e46", "#744244", "#7c4a52", "#8e5a60", "#a06a70"];
const RED_DARKER_BG = ["#522c34", "#4e282e", "#46242c", "#3a1c24", "#2e141c"];
const NEUTRAL_BG = "#1a2433";

const DEFAULT_RATIO_BG = {
  green: {
    anchor: 1.5,
    low_min: 1.0,
    high_max: 2.0,
    tier_count: 5,
    tier_max: 4,
    band_below: 0.1,
    band_above: 0.1,
  },
  red: {
    anchor: 0.75,
    low_min: 0.5,
    high_max: 1.0,
    tier_count: 5,
    tier_max: 4,
    band_below: 0.05,
    band_above: 0.05,
  },
};

const RATIO_THRESHOLD_DEFAULTS = {
  ratio_green_anchor: 1.5,
  ratio_green_low_min: 1.0,
  ratio_green_high_max: 2.0,
  ratio_green_tier_count: 5,
  ratio_red_anchor: 0.75,
  ratio_red_low_min: 0.5,
  ratio_red_high_max: 1.0,
  ratio_red_tier_count: 5,
};

function resolveRatioBgFromThresholds(thresholds) {
  const t = { ...RATIO_THRESHOLD_DEFAULTS, ...(thresholds || {}) };
  const greenTiers = Math.max(2, Math.min(10, Math.round(Number(t.ratio_green_tier_count) || 5)));
  const redTiers = Math.max(2, Math.min(10, Math.round(Number(t.ratio_red_tier_count) || 5)));
  const greenAnchor = Number(t.ratio_green_anchor);
  const greenLow = Number(t.ratio_green_low_min);
  const greenHigh = Number(t.ratio_green_high_max);
  const redAnchor = Number(t.ratio_red_anchor);
  const redLow = Number(t.ratio_red_low_min);
  const redHigh = Number(t.ratio_red_high_max);
  return {
    green: {
      anchor: greenAnchor,
      low_min: greenLow,
      high_max: greenHigh,
      tier_count: greenTiers,
      tier_max: greenTiers - 1,
      band_below: (greenAnchor - greenLow) / greenTiers,
      band_above: (greenHigh - greenAnchor) / greenTiers,
    },
    red: {
      anchor: redAnchor,
      low_min: redLow,
      high_max: redHigh,
      tier_count: redTiers,
      tier_max: redTiers - 1,
      band_below: (redAnchor - redLow) / redTiers,
      band_above: (redHigh - redAnchor) / redTiers,
    },
  };
}

function applyRatioBg(payload) {
  ratioBg =
    payload?.ratio_bg ||
    resolveRatioBgFromThresholds(payload?.thresholds) ||
    DEFAULT_RATIO_BG;
}

function fmtThreshold(v) {
  const n = Number(v);
  return Number.isFinite(n) ? `${n}` : "—";
}

function buildCockpitHelpClient(thresholds, ratio) {
  const t = thresholds || {};
  const g = ratio?.green || DEFAULT_RATIO_BG.green;
  const r = ratio?.red || DEFAULT_RATIO_BG.red;
  const trendBg = [
    `绿灯背景锚点 ${fmtThreshold(g.anchor)}（与季度/半季/月度/5-10交叉 绿灯一致）`,
    `区间 [${fmtThreshold(g.low_min)}, ${fmtThreshold(g.high_max)}]，锚点以下/以上各 ${g.tier_count} 档`,
    "比值 < 锚点变浅，> 锚点加深；超出区间取最浅/最深档",
    `红灯背景锚点 ${fmtThreshold(r.anchor)}（与四模块红灯一致）`,
    `区间 [${fmtThreshold(r.low_min)}, ${fmtThreshold(r.high_max)}]，锚点以下/以上各 ${r.tier_count} 档`,
    "比值 < 锚点加深，> 锚点变浅",
  ];
  const trendState = [
    "≥ Overbought 下限 → OVERBOUGHT（绿灯）",
    "≤ Oversold 上限 → OVERSOLD（红灯）",
    "介于两者之间且 ≥ 1 → NORMAL（绿灯，强度随比值升高）",
    "< 1 且未 Oversold → NORMAL（红灯，强度随比值降低）",
  ];
  return [
    {
      title: "季度趋势",
      lines: ["Up25%Q > Down25%Q → 绿灯 BULL", "否则 → 红灯 BEAR", "背景：与对应灯色满强度一致"],
    },
    {
      title: "半季趋势",
      lines: ["Up13%/34D > Down13%/34D → 绿灯 BULL", "否则 → 红灯 BEAR", "背景：与对应灯色满强度一致"],
    },
    {
      title: "月度趋势",
      lines: ["Up25%M > Down25%M → 绿灯 BULLISH", "否则 → 红灯 BEARISH", "背景：与对应灯色满强度一致"],
    },
    {
      title: "5-10交叉",
      lines: ["5日 ratio ≥ 10日 ratio → 绿灯 LONG", "否则 → 红灯 SHORT", "背景：与对应灯色满强度一致"],
    },
    {
      title: "10日趋势",
      lines: [
        `10D Overbought ≥ ${fmtThreshold(t.trend10_overbought_min ?? 2)}；Oversold ≤ ${fmtThreshold(t.trend10_oversold_max ?? 0.5)}`,
        ...trendState,
        ...trendBg,
      ],
    },
    {
      title: "5日趋势",
      lines: [
        `5D Overbought ≥ ${fmtThreshold(t.trend5_overbought_min ?? 2)}；Oversold ≤ ${fmtThreshold(t.trend5_oversold_max ?? 0.5)}`,
        ...trendState,
        ...trendBg,
      ],
    },
    {
      title: "极值提醒（T2108）",
      lines: [
        `≤ ${fmtThreshold(t.t2108_red_max ?? 20)} → OVERSOLD（红灯）`,
        `≥ ${fmtThreshold(t.t2108_green_min ?? 60)} → OVERBOUGHT（绿灯）`,
        "介于两者之间 → NORMAL（白灯）",
      ],
    },
  ];
}

function intensityToTier(intensity) {
  const t = Math.max(0, Math.min(1, Number(intensity ?? 0)));
  if (t >= 0.999) return 4;
  return Math.min(4, Math.round(t * 4));
}

function pickTierColor(palette, tierMax, idx) {
  if (tierMax <= 0) return palette[0];
  const slot = Math.min(tierMax, Math.max(0, idx));
  const scaled = Math.round((slot / tierMax) * (palette.length - 1));
  return palette[scaled];
}

/** 5/10 绿：锚点=四模块绿灯；以下变浅、以上加深（参数来自配置） */
function ratioGreenTrendBackground(v) {
  const g = ratioBg?.green || DEFAULT_RATIO_BG.green;
  if (!Number.isFinite(v)) return GREEN_BASELINE_BG;
  if (Math.abs(v - g.anchor) < 1e-6) return GREEN_BASELINE_BG;
  if (v > g.anchor && v <= g.high_max) {
    const idx = Math.min(g.tier_max, Math.floor((v - g.anchor) / g.band_above));
    return pickTierColor(GREEN_DARKER_BG, g.tier_max, idx);
  }
  if (v >= g.low_min && v < g.anchor) {
    const idx = Math.min(g.tier_max, Math.floor((g.anchor - v) / g.band_below));
    return pickTierColor(GREEN_LIGHTER_BG, g.tier_max, idx);
  }
  if (v < g.low_min) return pickTierColor(GREEN_LIGHTER_BG, g.tier_max, g.tier_max);
  return pickTierColor(GREEN_DARKER_BG, g.tier_max, g.tier_max);
}

/** 5/10 红：锚点=四模块红灯；以下加深、以上变浅 */
function ratioRedTrendBackground(v) {
  const r = ratioBg?.red || DEFAULT_RATIO_BG.red;
  if (!Number.isFinite(v)) return RED_BASELINE_BG;
  if (Math.abs(v - r.anchor) < 1e-6) return RED_BASELINE_BG;
  if (v > r.anchor && v <= r.high_max) {
    const idx = Math.min(r.tier_max, Math.floor((v - r.anchor) / r.band_above));
    return pickTierColor(RED_LIGHTER_BG, r.tier_max, idx);
  }
  if (v >= r.low_min && v < r.anchor) {
    const idx = Math.min(r.tier_max, Math.floor((r.anchor - v) / r.band_below));
    return pickTierColor(RED_DARKER_BG, r.tier_max, idx);
  }
  if (v < r.low_min) return pickTierColor(RED_DARKER_BG, r.tier_max, r.tier_max);
  return pickTierColor(RED_LIGHTER_BG, r.tier_max, r.tier_max);
}

function ratioTrendBackground(color, rawValue) {
  const v = Number(rawValue);
  if (color === "red") return ratioRedTrendBackground(v);
  return ratioGreenTrendBackground(v);
}

function cockpitPalette(color, intensity) {
  const tier = intensityToTier(intensity);
  if (color === "green") {
    return {
      background: GREEN_BASELINE_BG,
      lampClass: `cockpit-lamp cockpit-lamp-green cockpit-lamp-t${tier}`,
    };
  }
  if (color === "red") {
    return {
      background: RED_BASELINE_BG,
      lampClass: `cockpit-lamp cockpit-lamp-red cockpit-lamp-t${tier}`,
    };
  }
  return {
    background: NEUTRAL_BG,
    lampClass: "cockpit-lamp cockpit-lamp-white cockpit-lamp-t0",
  };
}

function modulePalette(key, module) {
  const isRatioTrend = key === "trend_10d" || key === "trend_5d";
  if (isRatioTrend && (module.color === "green" || module.color === "red")) {
    return {
      background: ratioTrendBackground(module.color, module.value),
      lampClass: cockpitPalette(module.color, module.intensity).lampClass,
    };
  }
  return cockpitPalette(module.color, module.intensity);
}

function renderStatusCards(payload) {
  const wrap = document.getElementById("breadthStatusCards");
  if (!wrap) return;
  const status = payload.status || {};
  const coverage = payload.coverage || {};
  const coverageInline = document.getElementById("coverageInline");
  if (coverageInline) {
    coverageInline.textContent = `History Coverage ${coverage.first_date || "—"} → ${coverage.last_date || "—"} (${coverage.row_count || 0}天)`;
  }
  const modules = [
    ["quarter_trend", status.quarter_trend],
    ["half_season_trend", status.half_season_trend],
    ["monthly_trend", status.monthly_trend],
    ["cross_5_10", status.cross_5_10],
    ["trend_10d", status.trend_10d],
    ["trend_5d", status.trend_5d],
    ["extreme_alert", status.extreme_alert],
  ].filter(([, m]) => Boolean(m));

  wrap.innerHTML = `
    ${modules.map(([key, m]) => {
      const pal = modulePalette(key, m);
      const active = activeCockpitKey === key ? " is-active" : "";
      return `
      <article class="status-card cockpit-card cockpit-card-opaque cockpit-card-link${active}" data-cockpit-key="${key}" role="button" tabindex="0" title="点击联动图表">
        <div class="status-label">${m.title}</div>
        <div class="status-value phase-row">
          <span class="${pal.lampClass}" aria-hidden="true"></span>
          <span>${m.state}</span>
        </div>
        <div class="status-note">${m.value ?? ""}</div>
      </article>
    `;
    }).join("")}
  `;
  bindCockpitCardLinkage(wrap);
}

function fadeChartColor(color, alpha) {
  if (typeof color !== "string") return color;
  if (color.startsWith("#") && color.length >= 7) {
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return color;
}

function cacheDatasetLinkStyle(chart) {
  chart.data.datasets.forEach((ds) => {
    if (ds._linkBaseColor == null) ds._linkBaseColor = ds.borderColor;
    if (ds._linkBaseWidth == null) ds._linkBaseWidth = ds.borderWidth ?? 1.2;
  });
}

function registerChart(canvasId, chart) {
  chartByCanvas[canvasId] = chart;
  cacheDatasetLinkStyle(chart);
}

function updateCockpitActiveUi() {
  document.querySelectorAll(".cockpit-card-link").forEach((el) => {
    el.classList.toggle("is-active", el.dataset.cockpitKey === activeCockpitKey);
  });
}

function applyChartLinkage() {
  const link = activeCockpitKey ? COCKPIT_CHART_LINK[activeCockpitKey] : null;
  const highlightSet = new Set(link?.datasets || []);

  Object.entries(chartByCanvas).forEach(([canvasId, chart]) => {
    const isTarget = link && canvasId === link.canvasId;
    chart.data.datasets.forEach((ds) => {
      const base = ds._linkBaseColor ?? ds.borderColor;
      const baseW = ds._linkBaseWidth ?? 1.2;
      if (!link) {
        ds.borderColor = base;
        ds.borderWidth = baseW;
        return;
      }
      if (!isTarget) {
        ds.borderColor = fadeChartColor(base, 0.22);
        ds.borderWidth = baseW * 0.75;
      } else if (highlightSet.has(ds.label)) {
        ds.borderColor = base;
        ds.borderWidth = Math.max(2.8, baseW * 2.2);
      } else {
        ds.borderColor = fadeChartColor(base, 0.28);
        ds.borderWidth = baseW * 0.65;
      }
    });
    chart.update("none");
  });

  document.querySelectorAll(".chart-card").forEach((card) => card.classList.remove("is-linked"));
  if (link) {
    const canvas = document.getElementById(link.canvasId);
    const card = canvas?.closest(".chart-card");
    card?.classList.add("is-linked");
    card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function onCockpitCardActivate(key) {
  if (!COCKPIT_CHART_LINK[key]) return;
  activeCockpitKey = activeCockpitKey === key ? null : key;
  updateCockpitActiveUi();
  applyChartLinkage();
}

function bindCockpitCardLinkage(wrap) {
  if (!wrap || cockpitClickBound) return;
  cockpitClickBound = true;
  wrap.addEventListener("click", (e) => {
    const card = e.target.closest("[data-cockpit-key]");
    if (!card) return;
    onCockpitCardActivate(card.dataset.cockpitKey);
  });
  wrap.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const card = e.target.closest("[data-cockpit-key]");
    if (!card) return;
    e.preventDefault();
    onCockpitCardActivate(card.dataset.cockpitKey);
  });
}

function renderCockpitHelp(payload) {
  const box = document.getElementById("cockpitHelpContent");
  if (!box) return;
  let sections = payload?.cockpit_help || [];
  if (!sections.length) {
    sections = buildCockpitHelpClient(payload?.thresholds, ratioBg);
  }
  if (!sections.length) {
    box.innerHTML = '<p class="hint">暂无说明（请刷新页面或重启后端服务）。</p>';
    return;
  }
  box.innerHTML = sections
    .map(
      (s) => `
      <article class="cockpit-help-item">
        <h3>${s.title}</h3>
        <ul>${(s.lines || []).map((line) => `<li>${line}</li>`).join("")}</ul>
      </article>
    `,
    )
    .join("");
}

function renderPercentileCards(payload) {
  const wrap = document.getElementById("breadthPercentileCards");
  if (!wrap) return;
  const cards = payload.percentile_cards || [];
  if (!cards.length) {
    wrap.innerHTML = '<p class="hint">暂无历史分位数据。</p>';
    return;
  }
  wrap.innerHTML = cards
    .map((c) => `
      <article class="pct-card">
        <div class="pct-title">${c.label}</div>
        <div class="pct-value">${c.value}</div>
        <div class="pct-meta">历史百分位 ${c.history_percentile}%</div>
        <div class="pct-strip-wrap">
          <div class="pct-strip"></div>
          <div class="pct-triangle" style="left:${clampPos(c.history_percentile)}%"></div>
          <div class="pct-strip-labels"><span>低位</span><span>中位</span><span>高位</span></div>
        </div>
      </article>
    `)
    .join("");
}

function renderBreadthConfig(payload) {
  const box = document.getElementById("breadthThresholdForm");
  if (!box) return;
  const t = payload?.thresholds || {};
  const fields = [
    { type: "title", label: "状态灯阈值" },
    ["trend10_overbought_min", "10D Overbought ≥", 0.01],
    ["trend10_oversold_max", "10D Oversold ≤", 0.01],
    ["trend5_overbought_min", "5D Overbought ≥", 0.01],
    ["trend5_oversold_max", "5D Oversold ≤", 0.01],
    ["t2108_red_max", "T2108 Red ≤", 0.01],
    ["t2108_green_min", "T2108 Green ≥", 0.01],
    { type: "title", label: "5/10 日背景分档（绿）" },
    ["ratio_green_anchor", "绿锚点", 0.01],
    ["ratio_green_low_min", "绿下限", 0.01],
    ["ratio_green_high_max", "绿上限", 0.01],
    ["ratio_green_tier_count", "绿侧档数", 1],
    { type: "title", label: "5/10 日背景分档（红）" },
    ["ratio_red_anchor", "红锚点", 0.01],
    ["ratio_red_low_min", "红下限", 0.01],
    ["ratio_red_high_max", "红上限", 0.01],
    ["ratio_red_tier_count", "红侧档数", 1],
  ];
  box.innerHTML = fields
    .map((item) => {
      if (item.type === "title") {
        return `<div class="config-section-title">${item.label}</div>`;
      }
      const [key, label, step] = item;
      return `
      <label>${label}
        <input type="number" id="breadthCfg_${key}" step="${step}" value="${t[key] ?? ""}" />
      </label>
    `;
    })
    .join("");
}

async function saveBreadthConfig() {
  const status = document.getElementById("breadthConfigStatus");
  const keys = [
    "trend10_overbought_min",
    "trend10_oversold_max",
    "trend5_overbought_min",
    "trend5_oversold_max",
    "t2108_red_max",
    "t2108_green_min",
    "ratio_green_anchor",
    "ratio_green_low_min",
    "ratio_green_high_max",
    "ratio_green_tier_count",
    "ratio_red_anchor",
    "ratio_red_low_min",
    "ratio_red_high_max",
    "ratio_red_tier_count",
  ];
  const thresholds = {};
  keys.forEach((k) => {
    const v = Number(document.getElementById(`breadthCfg_${k}`)?.value);
    if (Number.isFinite(v)) thresholds[k] = v;
  });
  const payload = await fetchJson("/api/breadth/config", {
    method: "PUT",
    body: JSON.stringify({ thresholds }),
  });
  renderBreadthConfig(payload);
  status.textContent = "配置已保存，正在刷新驾驶舱…";
  await loadBreadth(false);
  status.textContent = "配置已保存";
}

async function pollSyncProgress() {
  const txt = document.getElementById("syncProgressText");
  if (!txt) return;
  const p = await fetchJson("/api/breadth/sync-progress");
  if (p.status === "running") {
    const done = Number(p.processed || 0);
    const total = Number(p.total || 0);
    const pct = total > 0 ? `${Math.round((done * 100) / total)}%` : "--";
    txt.textContent = `同步中 ${done}/${total || "?"} (${pct})`;
    return false;
  }
  if (p.status === "done") {
    txt.textContent = `同步完成（${p.mode || ""}，${p.elapsed_seconds || 0}s）`;
    return true;
  }
  if (p.status === "error") {
    txt.textContent = `同步失败：${p.error || "unknown"}`;
    return true;
  }
  txt.textContent = "";
  return true;
}

function stopSyncPolling() {
  if (syncPollingTimer) {
    clearInterval(syncPollingTimer);
    syncPollingTimer = null;
  }
}

function startSyncPolling(onDone) {
  stopSyncPolling();
  syncPollingTimer = setInterval(async () => {
    try {
      const done = await pollSyncProgress();
      if (done) {
        stopSyncPolling();
        if (onDone) onDone();
      }
    } catch (err) {
      stopSyncPolling();
      console.error(err);
    }
  }, 1200);
}

function destroyCharts() {
  chartInstances.forEach((chart) => chart && chart.destroy());
  chartInstances = [];
  chartByCanvas = {};
}

function lineDataset(partial) {
  return {
    tension: 0.2,
    borderWidth: 1.2,
    pointRadius: 0,
    pointHoverRadius: 3,
    pointHitRadius: 10,
    ...partial,
  };
}

function chartOptions(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: "#dbe7f5" } },
      tooltip: { enabled: true },
    },
    ...extra,
  };
}

function renderCharts(payload) {
  const sourceRows = payload._all_rows || payload.rows || [];
  const maxRows = currentChartDays > 0 ? currentChartDays : sourceRows.length;
  const rows = [...sourceRows].slice(0, maxRows).reverse();
  if (!rows.length) return;
  const labels = rows.map((r) => r.raw_date || r.date);
  destroyCharts();

  const ratioChart = new Chart(document.getElementById("ratioChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "5 Day Ratio", data: rows.map((r) => toNum(r.c3_num)), borderColor: "#34d399" }),
        lineDataset({ label: "10 Day Ratio", data: rows.map((r) => toNum(r.c4_num)), borderColor: "#fbbf24" }),
        lineDataset({ label: "T2108", data: rows.map((r) => toNum(r.c14_num)), borderColor: "#60a5fa", yAxisID: "y1" }),
      ],
    },
    options: chartOptions({
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
        y1: { position: "right", ticks: { color: "#9fb2cc" }, grid: { drawOnChartArea: false } },
      },
    }),
  });
  chartInstances.push(ratioChart);
  registerChart("ratioChart", ratioChart);

  const upDown4Chart = new Chart(document.getElementById("upDown4Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 4%+", data: rows.map((r) => toNum(r.c1_num)), borderColor: "#22c55e" }),
        lineDataset({ label: "Down 4%+", data: rows.map((r) => toNum(r.c2_num)), borderColor: "#ef4444" }),
      ],
    },
    options: chartOptions({
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    }),
  });
  chartInstances.push(upDown4Chart);
  registerChart("upDown4Chart", upDown4Chart);

  const quarter25Chart = new Chart(document.getElementById("quarter25Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 25% Quarter", data: rows.map((r) => toNum(r.c5_num)), borderColor: "#22c55e" }),
        lineDataset({ label: "Down 25% Quarter", data: rows.map((r) => toNum(r.c6_num)), borderColor: "#ef4444" }),
      ],
    },
    options: chartOptions({
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    }),
  });
  chartInstances.push(quarter25Chart);
  registerChart("quarter25Chart", quarter25Chart);

  const month25Chart = new Chart(document.getElementById("month25Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 25% Month", data: rows.map((r) => toNum(r.c7_num)), borderColor: "#2dd4bf" }),
        lineDataset({ label: "Down 25% Month", data: rows.map((r) => toNum(r.c8_num)), borderColor: "#f97316" }),
      ],
    },
    options: chartOptions({
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    }),
  });
  chartInstances.push(month25Chart);
  registerChart("month25Chart", month25Chart);

  const extreme50Chart = new Chart(document.getElementById("extreme50Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 50% Month", data: rows.map((r) => toNum(r.c9_num)), borderColor: "#f59e0b" }),
        lineDataset({ label: "Down 50% Month", data: rows.map((r) => toNum(r.c10_num)), borderColor: "#ef4444" }),
      ],
    },
    options: chartOptions({
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    }),
  });
  chartInstances.push(extreme50Chart);
  registerChart("extreme50Chart", extreme50Chart);

  const spxBreadthChart = new Chart(document.getElementById("spxBreadthChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "S&P", data: rows.map((r) => toNum((r.c15 || "").replace(",", ""))), borderColor: "#60a5fa", yAxisID: "y" }),
        lineDataset({ label: "Up 13%/34D", data: rows.map((r) => toNum(r.c11_num)), borderColor: "#22c55e", yAxisID: "y1" }),
        lineDataset({ label: "Down 13%/34D", data: rows.map((r) => toNum(r.c12_num)), borderColor: "#ef4444", yAxisID: "y1" }),
      ],
    },
    options: chartOptions({
      scales: {
        x: { ticks: { color: "#9fb2cc", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { position: "left", ticks: { color: "#9fb2cc" }, grid: { color: "rgba(255,255,255,0.06)" } },
        y1: { position: "right", ticks: { color: "#9fb2cc" }, grid: { drawOnChartArea: false } },
      },
    }),
  });
  chartInstances.push(spxBreadthChart);
  registerChart("spxBreadthChart", spxBreadthChart);
  applyChartLinkage();
}

async function loadBreadth(refresh = false) {
  const btn = document.getElementById("refreshBreadthBtn");
  btn.disabled = true;
  btn.textContent = "刷新中…";
  try {
    const payload = await fetchJson(`/api/breadth?limit=8000${refresh ? "&refresh=true" : ""}`);
    latestPayload = { ...payload, _all_rows: payload.rows || [] };
    applyRatioBg(payload);
    renderStatusCards(payload);
    renderCockpitHelp(payload);
    renderPercentileCards(payload);
    renderBreadthConfig(payload);
    renderTable(payload);
    renderCharts(latestPayload);
    const updatedAt = payload.updated_at ? new Date(payload.updated_at).toLocaleString("zh-CN", { hour12: false }) : "—";
    document.getElementById("breadthMeta").textContent = `记录数 ${payload.row_count}，展示 ${payload.rows.length}，更新时间 ${updatedAt}`;
    document.getElementById("explainLink").href = payload.notes?.indicators_explain_url || "https://stockbee.blogspot.com/2022/12/market-monitor-scans.html";
  } catch (err) {
    showToast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "增量同步今日数据";
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

async function autoMorningBreadthRefresh() {
  const stampKey = `breadth:auto-refresh:${bjDateKey()}`;
  if (bjHourNow() >= BREADTH_MORNING_SYNC_HOUR_BJ && localStorage.getItem(stampKey) !== "done") {
    await loadBreadth(true);
    localStorage.setItem(stampKey, "done");
    return;
  }
  await loadBreadth(false);
}

async function startBreadthSync(full) {
  await fetchJson(`/api/breadth/sync?full=${full ? "true" : "false"}&async_mode=true`, { method: "POST" });
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
    startBreadthSync(false)
      .then(() => {
        startSyncPolling(async () => {
          await loadBreadth(false);
        });
      })
      .catch((err) => showToast(err.message, true));
  });
  document.getElementById("syncBreadthBtn").addEventListener("click", async () => {
    const btn = document.getElementById("syncBreadthBtn");
    btn.disabled = true;
    btn.textContent = "同步中…";
    try {
      await startBreadthSync(true);
      startSyncPolling(async () => {
        await loadBreadth(false);
      });
    } finally {
      btn.disabled = false;
      btn.textContent = "全量同步历史";
    }
  });
  document.getElementById("saveBreadthConfigBtn").addEventListener("click", () => {
    saveBreadthConfig().catch((err) => showToast(err.message, true));
  });
  document.querySelectorAll("#chartRangeGroup button").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentChartDays = Number(btn.dataset.days || 365);
      document.querySelectorAll("#chartRangeGroup button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      if (latestPayload) {
        renderCharts(latestPayload);
        applyChartLinkage();
      }
    });
  });
  pollSyncProgress().catch(() => {});
  autoMorningBreadthRefresh()
    .then(() => {})
    .catch((err) => showToast(err.message, true));
}

init();
