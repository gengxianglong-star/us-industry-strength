export type IndustryRow = {
  industry_key: string;
  name: string;
  stocks: number;
  score: number;
  perf_w: number;
  perf_m: number;
  perf_q: number;
  perf_h: number;
  perf_y: number;
  rank_w: number;
  rank_m: number;
  rank_q: number;
  rank_h: number;
  rank_y: number;
  finviz_url: string;
  is_top_strong?: boolean;
  excluded?: boolean;
  exclude_reason?: string;
  tier?: string;
  tags?: string[];
  stock_picks?: string[];
  stock_picks_error?: string;
  stock_screener_url?: string;
};

export type SnapshotPayload = {
  snapshot_date: string;
  top_strong_count?: number;
  industries: IndustryRow[];
  rs_meta?: Record<string, number | null | undefined>;
  rs_count?: number;
};

export type WatchlistRow = {
  symbol: string;
  rs_rank: number;
  rs_score: number;
  industries?: string[];
};

export type RsPayload = {
  snapshot_date: string;
  rows: Array<Record<string, unknown>>;
  watchlist: WatchlistRow[];
  new_stock_leaderboard: Array<Record<string, unknown>>;
  rs_meta?: Record<string, number | null | undefined>;
};

export type AutomationStatus = {
  lag_days?: number;
  target_date?: string;
  display_date?: string;
  daily_status?: string;
  headline?: string;
  has_snapshot?: boolean;
};

const LEGACY_TAG_LABEL: Record<string, string> = {
  "加速↑": "A↑",
  "加速↓": "A↓",
  加速: "A",
  "回调↑": "PB↑",
  "回调↓": "PB↓",
  回调: "PB",
  "Accel↑": "A↑",
  "Accel↓": "A↓",
  Accel: "A",
  "Pullback↑": "PB↑",
  "Pullback↓": "PB↓",
  Pullback: "PB",
};

function buildTrendLabel(base: string, arrow: string) {
  return `${base}${arrow}`;
}

export function normalizeTrendLabel(text: string) {
  return LEGACY_TAG_LABEL[text] || text;
}

export function trendBadgeClass(text: string) {
  const t = normalizeTrendLabel(text);
  if (t === "A↑") return "trend-badge trend-accel-up";
  if (t === "A↓") return "trend-badge trend-accel-down";
  if (t === "PB↓") return "trend-badge trend-pullback-down";
  if (t === "PB↑") return "trend-badge trend-pullback-up";
  if (t === "A") return "trend-badge trend-accel-down";
  if (t === "PB") return "trend-badge trend-pullback-up";
  return "trend-badge";
}

export function computeShortTrend(row: IndustryRow) {
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

export function computeLongTrend(row: IndustryRow) {
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

export function getTopStrongIndustries(data: SnapshotPayload) {
  return data.industries.filter((i) => i.is_top_strong).sort((a, b) => b.score - a.score);
}

export function pct(v: number) {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

export function perfScales(rows: IndustryRow[]) {
  const keys = ["perf_w", "perf_m", "perf_q", "perf_h", "perf_y"] as const;
  const scales: Record<string, number> = {};
  keys.forEach((key) => {
    const vals = rows.map((r) => Math.abs(Number(r[key]))).filter(Number.isFinite);
    scales[key] = Math.max(...vals, 0.01);
  });
  return scales;
}

export function rankItemClass(rank: number) {
  if (rank <= 20) return "rank-hot";
  if (rank >= 100) return "rank-cold";
  return "rank-mid";
}

export function rankHeat(rank: number) {
  if (rank <= 20) return "rank-cell pos";
  if (rank >= 100) return "rank-cell neg";
  return "rank-cell";
}

export function finvizDailyChartUrl(symbol: string) {
  return `https://charts2.finviz.com/chart.ashx?t=${encodeURIComponent(symbol)}&ty=c&ta=1&p=d&s=l&theme=dark`;
}

export function rsUniverseCount(
  snapshot: SnapshotPayload | null,
  rsMeta?: Record<string, number | null | undefined> | null,
) {
  const meta = snapshot?.rs_meta || rsMeta;
  if (meta) {
    const newStock =
      (meta.new_stock_m_count ?? 0) +
      (meta.new_stock_q_count ?? 0) +
      (meta.new_stock_h_count ?? 0) +
      (meta.new_stock_3q_count ?? 0);
    const main = Number(meta.computed_count ?? 0);
    if (main || newStock) return main + newStock;
  }
  return snapshot?.rs_count && snapshot.rs_count > 0 ? snapshot.rs_count : null;
}
