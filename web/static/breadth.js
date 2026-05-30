let chartInstances = [];
let chartByCanvas = {};
let currentChartDays = 365;
let latestPayload = null;
let syncPollingTimer = null;
let syncAwaiting = false;
let ratioBg = null;
let activeCockpitKey = null;
let cockpitClickBound = false;
const BREADTH_MORNING_SYNC_HOUR_BJ = 6;

const COCKPIT_MODULE_TITLE = {
  quarter_trend: "Quarter",
  half_season_trend: "Half Qtr",
  monthly_trend: "Monthly",
  cross_5_10: "5-10 Cross",
  trend_10d: "10D Trend",
  trend_5d: "5D Trend",
  extreme_alert: "T2108",
};

const COCKPIT_HELP_TITLE = {
  quarter_trend: "Quarter Trend",
  half_season_trend: "Half Quarter Trend",
  monthly_trend: "Monthly Trend",
  cross_5_10: "5-10 Cross",
  trend_10d: "10D Trend",
  trend_5d: "5D Trend",
  extreme_alert: "T2108 Alert",
};

/** Cockpit card → chart canvas and highlighted series */
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
    const title = raw || headers[start] || "Metric";
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
    `Green anchor ${fmtThreshold(g.anchor)} (matches quarter/half/month/5-10 green lights)`,
    `Range [${fmtThreshold(g.low_min)}, ${fmtThreshold(g.high_max)}], ${g.tier_count} tiers below/above anchor`,
    "Below anchor = lighter; above = deeper; out of range = min/max shade",
    `Red anchor ${fmtThreshold(r.anchor)} (matches four red-light modules)`,
    `Range [${fmtThreshold(r.low_min)}, ${fmtThreshold(r.high_max)}], ${r.tier_count} tiers below/above anchor`,
    "Below anchor = deeper; above = lighter",
  ];
  const trendState = [
    "≥ overbought floor → OVERBOUGHT (green)",
    "≤ oversold cap → OVERSOLD (red)",
    "Between and ≥ 1 → NORMAL (green, stronger as ratio rises)",
    "< 1 and not oversold → NORMAL (red, weaker as ratio falls)",
  ];
  return [
    {
      id: "quarter_trend",
      title: COCKPIT_HELP_TITLE.quarter_trend,
      lines: ["Up25%Q > Down25%Q → green BULL", "else → red BEAR", "Background = full-strength light color"],
    },
    {
      id: "half_season_trend",
      title: COCKPIT_HELP_TITLE.half_season_trend,
      lines: ["Up13%/34D > Down13%/34D → green BULL", "else → red BEAR", "Background = full-strength light color"],
    },
    {
      id: "monthly_trend",
      title: COCKPIT_HELP_TITLE.monthly_trend,
      lines: ["Up25%M > Down25%M → green BULLISH", "else → red BEARISH", "Background = full-strength light color"],
    },
    {
      id: "cross_5_10",
      title: COCKPIT_HELP_TITLE.cross_5_10,
      lines: ["5D ratio ≥ 10D ratio → green LONG", "else → red SHORT", "Background = full-strength light color"],
    },
    {
      id: "trend_10d",
      title: COCKPIT_HELP_TITLE.trend_10d,
      lines: [
        `10D Overbought ≥ ${fmtThreshold(t.trend10_overbought_min ?? 2)}；Oversold ≤ ${fmtThreshold(t.trend10_oversold_max ?? 0.5)}`,
        ...trendState,
        ...trendBg,
      ],
    },
    {
      id: "trend_5d",
      title: COCKPIT_HELP_TITLE.trend_5d,
      lines: [
        `5D Overbought ≥ ${fmtThreshold(t.trend5_overbought_min ?? 2)}；Oversold ≤ ${fmtThreshold(t.trend5_oversold_max ?? 0.5)}`,
        ...trendState,
        ...trendBg,
      ],
    },
    {
      id: "extreme_alert",
      title: COCKPIT_HELP_TITLE.extreme_alert,
      lines: [
        `≤ ${fmtThreshold(t.t2108_red_max ?? 20)} → OVERSOLD (red)`,
        `≥ ${fmtThreshold(t.t2108_green_min ?? 60)} → OVERBOUGHT (green)`,
        "Between → NORMAL (neutral)",
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

function cockpitStatusBand(key, module, thresholds) {
  if (key === "trend_5d" || key === "trend_10d") {
    return ratioBandHtml(key, module, thresholds);
  }
  if (key === "extreme_alert") {
    return t2108BandHtml(module, thresholds);
  }
  return "";
}

function mapLinear(value, min, max) {
  if (!Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
    return 50;
  }
  return clampPos(((value - min) / (max - min)) * 100);
}

function renderStatusBand(leftLabel, rightLabel, pointerPct) {
  const pos = clampPos(pointerPct);
  return `
    <div class="status-band-wrap">
      <div class="status-band scale-green-red" aria-hidden="true"></div>
      <div class="status-pointer" style="left:${pos}%" aria-hidden="true"></div>
      <div class="status-band-labels"><span>${leftLabel}</span><span>${rightLabel}</span></div>
    </div>
  `;
}

function ratioBandHtml(key, module, thresholds) {
  const value = toNum(module.value);
  if (value == null) return "";
  const is5d = key === "trend_5d";
  const oversold = toNum(is5d ? thresholds.trend5_oversold_max : thresholds.trend10_oversold_max) ?? 0.5;
  const overbought = toNum(is5d ? thresholds.trend5_overbought_min : thresholds.trend10_overbought_min) ?? 2.0;
  const min = 0;
  const max = Math.max(overbought * 1.2, 2.4);
  return renderStatusBand(`≤${oversold}`, `≥${overbought}`, mapLinear(value, min, max));
}

function t2108BandHtml(module, thresholds) {
  const value = toNum(module.value);
  if (value == null) return "";
  const redMax = toNum(thresholds.t2108_red_max) ?? 20;
  const greenMin = toNum(thresholds.t2108_green_min) ?? 60;
  return renderStatusBand(`≤${redMax}`, `≥${greenMin}`, mapLinear(value, 0, 100));
}

function renderUpDownBar(up, down, upLabel, downLabel) {
  const u = Math.max(0, toNum(up) ?? 0);
  const d = Math.max(0, toNum(down) ?? 0);
  const total = u + d;
  if (total <= 0) return "";
  const upPct = (u / total) * 100;
  return `
    <div class="cockpit-balance-wrap">
      <div class="cockpit-balance-bar" aria-hidden="true">
        <span class="cockpit-balance-up" style="width:${upPct.toFixed(1)}%"></span>
        <span class="cockpit-balance-down" style="width:${(100 - upPct).toFixed(1)}%"></span>
      </div>
      <div class="cockpit-balance-meta">
        <span class="cockpit-balance-up-label">${Math.round(upPct)}% Up</span>
        <span class="cockpit-balance-note">${upLabel} ${u} · ${downLabel} ${d}</span>
      </div>
    </div>
  `;
}

function cockpitTrendBalance(key, latestRow) {
  if (!latestRow) return "";
  if (key === "quarter_trend") {
    return renderUpDownBar(latestRow.c5_num, latestRow.c6_num, "Up25Q", "Down25Q");
  }
  if (key === "half_season_trend") {
    return renderUpDownBar(latestRow.c11_num, latestRow.c12_num, "Up13", "Down13");
  }
  if (key === "monthly_trend") {
    return renderUpDownBar(latestRow.c7_num, latestRow.c8_num, "Up25M", "Down25M");
  }
  return "";
}

function upDownPct(up, down) {
  const u = Math.max(0, toNum(up) ?? 0);
  const d = Math.max(0, toNum(down) ?? 0);
  const total = u + d;
  return total > 0 ? (u / total) * 100 : 50;
}

function cockpitGaugePct(key, module, thresholds, latestRow) {
  if (key === "trend_5d" || key === "trend_10d") {
    const value = toNum(module.value);
    if (value == null) return 50;
    const is5d = key === "trend_5d";
    const overbought =
      toNum(is5d ? thresholds.trend5_overbought_min : thresholds.trend10_overbought_min) ?? 2.0;
    return mapLinear(value, 0, Math.max(overbought * 1.2, 2.4));
  }
  if (key === "extreme_alert") {
    return mapLinear(toNum(module.value), 0, 100);
  }
  if (key === "cross_5_10" && latestRow) {
    const ratio5 = toNum(latestRow.c3_num);
    if (ratio5 == null) return 50;
    const overbought = toNum(thresholds.trend5_overbought_min) ?? 2.0;
    return mapLinear(ratio5, 0, Math.max(overbought * 1.2, 2.4));
  }
  if (key === "quarter_trend" && latestRow) {
    return upDownPct(latestRow.c5_num, latestRow.c6_num);
  }
  if (key === "half_season_trend" && latestRow) {
    return upDownPct(latestRow.c11_num, latestRow.c12_num);
  }
  if (key === "monthly_trend" && latestRow) {
    return upDownPct(latestRow.c7_num, latestRow.c8_num);
  }
  return 50;
}

function gaugeStateClass(color) {
  if (color === "green") return "gauge-state-ok";
  if (color === "red") return "gauge-state-bad";
  return "gauge-state-neutral";
}

function formatCockpitGaugeValue(key, module, latestRow) {
  if (key === "trend_5d" || key === "trend_10d" || key === "extreme_alert") {
    const v = toNum(module.value);
    return v == null ? "" : String(v);
  }
  if (key === "cross_5_10" && latestRow) {
    const r5 = toNum(latestRow.c3_num);
    const r10 = toNum(latestRow.c4_num);
    if (r5 == null || r10 == null) return "";
    return `${r5.toFixed(2)} / ${r10.toFixed(2)}`;
  }
  if (
    (key === "quarter_trend" || key === "half_season_trend" || key === "monthly_trend") &&
    latestRow
  ) {
    const pairs = {
      quarter_trend: [latestRow.c5_num, latestRow.c6_num],
      half_season_trend: [latestRow.c11_num, latestRow.c12_num],
      monthly_trend: [latestRow.c7_num, latestRow.c8_num],
    };
    const [up, down] = pairs[key] || [];
    const u = Math.max(0, toNum(up) ?? 0);
    const d = Math.max(0, toNum(down) ?? 0);
    return `${Math.round(upDownPct(u, d))}% Up`;
  }
  return module.value != null ? String(module.value) : "";
}

function renderCockpitGauge({ gaugeKey, pct, state, value, colorClass }) {
  const p = clampPos(pct);
  const cx = 44;
  const cy = 44;
  const r = 32;
  const angle = Math.PI - (p / 100) * Math.PI;
  const nx = cx + (r - 10) * Math.cos(angle);
  const ny = cy - (r - 10) * Math.sin(angle);
  const dotX = cx + r * Math.cos(angle);
  const dotY = cy - r * Math.sin(angle);
  const gradId = `gauge-grad-${gaugeKey}`;
  const label = [state, value].filter(Boolean).join(" ");

  return `
    <div class="cockpit-gauge-wrap">
      <svg class="cockpit-gauge-svg" viewBox="0 0 88 46" role="img" aria-label="${label}">
        <defs>
          <linearGradient id="${gradId}" x1="8" y1="44" x2="80" y2="44" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#6a4040" stop-opacity="0.85" />
            <stop offset="50%" stop-color="#5a5a62" stop-opacity="0.45" />
            <stop offset="100%" stop-color="#3d6648" stop-opacity="0.85" />
          </linearGradient>
        </defs>
        <path class="gauge-arc-bg" d="M 12 44 A 32 32 0 0 1 76 44" />
        <path class="gauge-arc-fill" d="M 12 44 A 32 32 0 0 1 76 44" stroke="url(#${gradId})" />
        <line class="gauge-tick" x1="12" y1="44" x2="15" y2="41" />
        <line class="gauge-tick" x1="44" y1="12" x2="44" y2="15" />
        <line class="gauge-tick" x1="76" y1="44" x2="73" y2="41" />
        <line class="gauge-needle" x1="${cx}" y1="${cy}" x2="${nx.toFixed(2)}" y2="${ny.toFixed(2)}" />
        <circle class="gauge-hub" cx="${cx}" cy="${cy}" r="2.2" />
        <circle class="gauge-dot" cx="${dotX.toFixed(2)}" cy="${dotY.toFixed(2)}" r="2.4" />
      </svg>
      <div class="cockpit-gauge-caption">
        <span class="cockpit-gauge-state ${colorClass}">${state}</span>
        ${value ? `<span class="cockpit-gauge-value">${value}</span>` : ""}
      </div>
    </div>
  `;
}

function cockpitStateLabel(state) {
  return state || "—";
}

function cockpitHelpTitle(section) {
  if (section?.id && COCKPIT_HELP_TITLE[section.id]) return COCKPIT_HELP_TITLE[section.id];
  return section?.title || "";
}

function renderStatusCards(payload) {
  const wrap = document.getElementById("breadthStatusCards");
  if (!wrap) return;
  const status = payload.status || {};
  const thresholds = payload.thresholds || {};
  const latestRow = (payload.rows || [])[0] || null;
  const coverage = payload.coverage || {};
  const coverageInline = document.getElementById("coverageInline");
  if (coverageInline) {
    coverageInline.textContent = `History ${coverage.first_date || "—"} → ${coverage.last_date || "—"} (${coverage.row_count || 0} days)`;
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
      const active = activeCockpitKey === key ? " is-active" : "";
      const label = COCKPIT_MODULE_TITLE[key] || m.title;
      const pct = cockpitGaugePct(key, m, thresholds, latestRow);
      const gauge = renderCockpitGauge({
        gaugeKey: key,
        pct,
        state: cockpitStateLabel(m.state),
        value: formatCockpitGaugeValue(key, m, latestRow),
        colorClass: gaugeStateClass(m.color),
      });
      return `
      <article class="status-card cockpit-card cockpit-card-opaque cockpit-card-link${active}" data-cockpit-key="${key}" role="button" tabindex="0" title="Click to link chart · ${label}">
        <div class="status-label">${label}</div>
        ${gauge}
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
    box.innerHTML = '<p class="hint">No rules loaded — refresh or restart the server.</p>';
    return;
  }
  box.innerHTML = sections
    .map(
      (s) => `
      <article class="cockpit-help-item">
        <h3>${cockpitHelpTitle(s)}</h3>
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
    wrap.innerHTML = '<p class="hint">No percentile history yet.</p>';
    return;
  }
  wrap.innerHTML = cards
    .map((c) => `
      <article class="pct-card">
        <div class="pct-title">${c.label}</div>
        <div class="pct-value">${c.value}</div>
        <div class="pct-meta">${c.history_percentile}th pct</div>
        <div class="pct-strip-wrap">
          <div class="pct-strip"></div>
          <div class="pct-triangle" style="left:${clampPos(c.history_percentile)}%"></div>
          <div class="pct-strip-labels"><span>Low</span><span>Mid</span><span>High</span></div>
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
    { type: "title", label: "Status Light Thresholds" },
    ["trend10_overbought_min", "10D Overbought ≥", 0.01],
    ["trend10_oversold_max", "10D Oversold ≤", 0.01],
    ["trend5_overbought_min", "5D Overbought ≥", 0.01],
    ["trend5_oversold_max", "5D Oversold ≤", 0.01],
    ["t2108_red_max", "T2108 Red ≤", 0.01],
    ["t2108_green_min", "T2108 Green ≥", 0.01],
    { type: "title", label: "5/10D Background Tiers (Green)" },
    ["ratio_green_anchor", "Green anchor", 0.01],
    ["ratio_green_low_min", "Green low", 0.01],
    ["ratio_green_high_max", "Green high", 0.01],
    ["ratio_green_tier_count", "Green tiers", 1],
    { type: "title", label: "5/10D Background Tiers (Red)" },
    ["ratio_red_anchor", "Red anchor", 0.01],
    ["ratio_red_low_min", "Red low", 0.01],
    ["ratio_red_high_max", "Red high", 0.01],
    ["ratio_red_tier_count", "Red tiers", 1],
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
  status.textContent = "Saved — refreshing cockpit…";
  await loadBreadth(false);
  status.textContent = "Saved";
}

async function pollSyncProgress() {
  const txt = document.getElementById("syncProgressText");
  if (!txt) return !syncAwaiting;
  const p = await fetchJson("/api/breadth/sync-progress");
  if (p.status === "running") {
    const done = Number(p.processed || 0);
    const total = Number(p.total || 0);
    const pct = total > 0 ? `${Math.round((done * 100) / total)}%` : "--";
    txt.textContent = `Syncing ${done}/${total || "?"} (${pct})`;
    return false;
  }
  if (p.status === "done") {
    txt.textContent = `Done (${p.mode || ""}, ${p.elapsed_seconds || 0}s)`;
    syncAwaiting = false;
    return true;
  }
  if (p.status === "error") {
    txt.textContent = `Sync failed: ${p.error || "unknown"}`;
    syncAwaiting = false;
    showToast(p.error || "Breadth sync failed", true);
    return true;
  }
  if (syncAwaiting) {
    txt.textContent = "Waiting for sync…";
    return false;
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
  syncAwaiting = true;
  pollSyncProgress().catch(() => {});
  syncPollingTimer = setInterval(async () => {
    try {
      const done = await pollSyncProgress();
      if (done) {
        stopSyncPolling();
        syncAwaiting = false;
        if (onDone) await onDone();
      }
    } catch (err) {
      stopSyncPolling();
      syncAwaiting = false;
      showToast(err.message || "Sync progress check failed", true);
      console.error(err);
    }
  }, 1200);
}

function setSyncButtonsBusy(busy, label) {
  const refreshBtn = document.getElementById("refreshBreadthBtn");
  const syncBtn = document.getElementById("syncBreadthBtn");
  if (refreshBtn) {
    refreshBtn.disabled = busy;
    if (label && busy) refreshBtn.textContent = label;
    else if (!busy) refreshBtn.textContent = "Sync today";
  }
  if (syncBtn) {
    syncBtn.disabled = busy;
  }
}

async function runBreadthSync(full, { auto = false } = {}) {
  const progress = document.getElementById("syncProgressText");
  setSyncButtonsBusy(true, full ? "Full sync…" : "Incremental sync…");
  if (progress) progress.textContent = "Starting sync…";
  try {
    const kick = await fetchJson(
      `/api/breadth/sync?full=${full ? "true" : "false"}&async_mode=true`,
      { method: "POST" },
    );
    if (kick.status === "error") {
      throw new Error(kick.error || "Sync start failed");
    }
    if (kick.blocked) {
      if (progress) progress.textContent = "Sync already running — joining…";
    } else if (kick.status === "started") {
      if (progress) progress.textContent = "Sync started…";
    }
    await new Promise((resolve, reject) => {
      startSyncPolling(async () => {
        try {
          await loadBreadth(false);
          resolve();
        } catch (err) {
          reject(err);
        }
      });
    });
  } finally {
    setSyncButtonsBusy(false);
  }
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
    fill: false,
    ...partial,
  };
}

function chartScaleOptions(theme, extra = {}) {
  return {
    x: {
      ticks: { color: theme.text, maxTicksLimit: 8 },
      grid: { color: theme.grid },
    },
    y: {
      ticks: { color: theme.text },
      grid: { color: theme.grid },
    },
    ...extra,
  };
}

function chartOptions(theme, extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: theme.text } },
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
  const theme = chartThemeFromCss();
  destroyCharts();

  const ratioChart = new Chart(document.getElementById("ratioChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "5 Day Ratio", data: rows.map((r) => toNum(r.c3_num)), borderColor: theme.ok }),
        lineDataset({ label: "10 Day Ratio", data: rows.map((r) => toNum(r.c4_num)), borderColor: theme.warn }),
        lineDataset({ label: "T2108", data: rows.map((r) => toNum(r.c14_num)), borderColor: theme.accent, yAxisID: "y1" }),
      ],
    },
    options: chartOptions(theme, {
      scales: chartScaleOptions(theme, {
        y1: { position: "right", ticks: { color: theme.text }, grid: { drawOnChartArea: false } },
      }),
    }),
  });
  chartInstances.push(ratioChart);
  registerChart("ratioChart", ratioChart);

  const upDown4Chart = new Chart(document.getElementById("upDown4Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 4%+", data: rows.map((r) => toNum(r.c1_num)), borderColor: theme.ok }),
        lineDataset({ label: "Down 4%+", data: rows.map((r) => toNum(r.c2_num)), borderColor: theme.bad }),
      ],
    },
    options: chartOptions(theme, { scales: chartScaleOptions(theme) }),
  });
  chartInstances.push(upDown4Chart);
  registerChart("upDown4Chart", upDown4Chart);

  const quarter25Chart = new Chart(document.getElementById("quarter25Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 25% Quarter", data: rows.map((r) => toNum(r.c5_num)), borderColor: theme.ok }),
        lineDataset({ label: "Down 25% Quarter", data: rows.map((r) => toNum(r.c6_num)), borderColor: theme.bad }),
      ],
    },
    options: chartOptions(theme, { scales: chartScaleOptions(theme) }),
  });
  chartInstances.push(quarter25Chart);
  registerChart("quarter25Chart", quarter25Chart);

  const month25Chart = new Chart(document.getElementById("month25Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 25% Month", data: rows.map((r) => toNum(r.c7_num)), borderColor: theme.ok }),
        lineDataset({ label: "Down 25% Month", data: rows.map((r) => toNum(r.c8_num)), borderColor: theme.bad }),
      ],
    },
    options: chartOptions(theme, { scales: chartScaleOptions(theme) }),
  });
  chartInstances.push(month25Chart);
  registerChart("month25Chart", month25Chart);

  const extreme50Chart = new Chart(document.getElementById("extreme50Chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({ label: "Up 50% Month", data: rows.map((r) => toNum(r.c9_num)), borderColor: theme.ok }),
        lineDataset({ label: "Down 50% Month", data: rows.map((r) => toNum(r.c10_num)), borderColor: theme.bad }),
      ],
    },
    options: chartOptions(theme, { scales: chartScaleOptions(theme) }),
  });
  chartInstances.push(extreme50Chart);
  registerChart("extreme50Chart", extreme50Chart);

  const spxBreadthChart = new Chart(document.getElementById("spxBreadthChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        lineDataset({
          label: "S&P",
          data: rows.map((r) => toNum((r.c15 || "").replace(",", ""))),
          borderColor: theme.accent,
          yAxisID: "y",
        }),
        lineDataset({ label: "Up 13%/34D", data: rows.map((r) => toNum(r.c11_num)), borderColor: theme.ok, yAxisID: "y1" }),
        lineDataset({ label: "Down 13%/34D", data: rows.map((r) => toNum(r.c12_num)), borderColor: theme.bad, yAxisID: "y1" }),
      ],
    },
    options: chartOptions(theme, {
      scales: chartScaleOptions(theme, {
        y: { position: "left", ticks: { color: theme.text }, grid: { color: theme.grid } },
        y1: { position: "right", ticks: { color: theme.text }, grid: { drawOnChartArea: false } },
      }),
    }),
  });
  chartInstances.push(spxBreadthChart);
  registerChart("spxBreadthChart", spxBreadthChart);
  applyChartLinkage();
}

async function loadBreadth(refresh = false) {
  const btn = document.getElementById("refreshBreadthBtn");
  const wasDisabled = btn?.disabled;
  if (btn && !wasDisabled) {
    btn.disabled = true;
    btn.textContent = "Loading…";
  }
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
    document.getElementById("breadthMeta").textContent = `${payload.row_count} rows · showing ${payload.rows.length} · updated ${updatedAt}`;
    document.getElementById("explainLink").href = payload.notes?.indicators_explain_url || "https://stockbee.blogspot.com/2022/12/market-monitor-scans.html";
  } catch (err) {
    showToast(err.message, true);
  } finally {
    if (btn && !wasDisabled && !syncAwaiting) {
      btn.disabled = false;
      btn.textContent = "Sync today";
    }
  }
}

async function autoMorningBreadthRefresh() {
  const stampKey = `breadth:auto-refresh:${bjDateKey()}`;
  const shouldSync =
    bjHourNow() >= BREADTH_MORNING_SYNC_HOUR_BJ && localStorage.getItem(stampKey) !== "done";
  if (shouldSync) {
    try {
      await runBreadthSync(false, { auto: true });
      localStorage.setItem(stampKey, "done");
      return;
    } catch (err) {
      showToast(`Auto-sync failed — showing cache: ${err.message}`, true);
    }
  }
  await loadBreadth(false);
}

async function startBreadthSync(full) {
  await runBreadthSync(full);
}

function init() {
  renderHealthBadge("healthBadge").catch(() => {});
  const widthRange = document.getElementById("chartWidthRange");
  const widthValue = document.getElementById("chartWidthValue");
  const chartPanel = document.querySelector(".chart-panel");
  const setChartWidth = (val) => {
    widthValue.textContent = `${val}%`;
    chartPanel?.style.setProperty("--charts-width", `${val}%`);
  };
  setChartWidth(widthRange.value);
  widthRange.addEventListener("input", (e) => setChartWidth(e.target.value));

  document.getElementById("refreshBreadthBtn")?.addEventListener("click", () => {
    runBreadthSync(false).catch((err) => showToast(err.message, true));
  });
  document.getElementById("syncBreadthBtn")?.addEventListener("click", () => {
    runBreadthSync(true).catch((err) => showToast(err.message, true));
  });
  document.getElementById("saveBreadthConfigBtn")?.addEventListener("click", () => {
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
  loadBreadth(false).catch((err) => showToast(err.message, true));
}

init();
