import type { IndustryRow } from "./industry";

export type Quadrant = "leaders" | "ignition" | "weakening" | "lagging";

export type RotationNode = {
  industry_key: string;
  name: string;
  rs_score: number;
  rs_3m: number;
  rs_1m: number;
  delta_1w: number;
  rs_velocity: number;
  quadrant: Quadrant;
  isAlpha: boolean;
  finviz_url: string;
  stock_picks: string[];
  trendState: string;
  trendTone: TrendTone;
};

export type TrendTone = "expansion" | "pullback" | "bear" | "neutral" | "reversion";

export type AlphaFilter = "momentum" | "ignition" | "oversold" | "pullback";

export function rsFromRank(rank: number) {
  if (!Number.isFinite(rank) || rank <= 0) return 50;
  return Math.max(1, Math.min(100, 101 - rank));
}

/** 1M rank delta vs prior snapshot (positive = rank improved). */
export function rsVelocity1M(row: IndustryRow): number {
  const delta = row.vs_previous?.rank_m_delta;
  if (delta != null && Number.isFinite(delta)) return delta;
  return row.rank_q - row.rank_m;
}

/** 1W rank momentum: positive when week rank is stronger than month rank. */
export function rsDelta1W(row: IndustryRow): number {
  if (!Number.isFinite(row.rank_m) || !Number.isFinite(row.rank_w)) return 0;
  return row.rank_m - row.rank_w;
}

export function classifyQuadrant3m1m(rs3m: number, rs1m: number): Quadrant {
  if (rs3m >= 50 && rs1m >= 50) return "leaders";
  if (rs3m < 50 && rs1m >= 50) return "ignition";
  if (rs3m >= 50 && rs1m < 50) return "weakening";
  return "lagging";
}

export function quadrantLabel(q: Quadrant) {
  const labels: Record<Quadrant, string> = {
    leaders: "Leaders",
    ignition: "Ignition",
    weakening: "Stalling",
    lagging: "Lagging",
  };
  return labels[q];
}

export function quadrantDotColor(q: Quadrant) {
  const colors: Record<Quadrant, string> = {
    leaders: "#10b981",
    ignition: "#06b6d4",
    weakening: "#f59e0b",
    lagging: "#ef4444",
  };
  return colors[q];
}

export function computeTrendState(row: IndustryRow, breadthRatio10 = 1): {
  trendState: string;
  trendTone: TrendTone;
} {
  const rs6m = rsFromRank(row.rank_h);
  const rs3m = rsFromRank(row.rank_q);
  const rs1m = rsFromRank(row.rank_m);
  const rs1w = rsFromRank(row.rank_w);
  const velocity = rsVelocity1M(row);

  if (row.excluded || (rs6m < 40 && rs1m < rs6m)) {
    return { trendState: "Structural Bear", trendTone: "bear" };
  }

  if (rs6m > 90 && rs1m > rs3m && rs3m > rs6m) {
    return { trendState: "Aggressive Expansion", trendTone: "expansion" };
  }

  if (rs6m < 60 && rs1w > 90 && breadthRatio10 > 2.0) {
    return { trendState: "Momentum Ignition", trendTone: "expansion" };
  }
  if (rs6m < 50 && velocity > 12 && rs1w > 75) {
    return { trendState: "Momentum Ignition", trendTone: "expansion" };
  }

  if (rs6m > 85 && row.rank_w > row.rank_m && row.rank_m <= row.rank_q) {
    return { trendState: "Constructive Pullback", trendTone: "pullback" };
  }

  if (rs6m > 70 && velocity < 0) {
    return { trendState: "Stalling / Climax", trendTone: "pullback" };
  }

  if (rs6m < 20 && row.rank_w < row.rank_m && velocity > 0) {
    return { trendState: "Mean Reversion", trendTone: "reversion" };
  }

  if (velocity > 5 && rs6m < 55) {
    return { trendState: "Mean Reversion", trendTone: "reversion" };
  }

  return { trendState: "Steady Accumulation", trendTone: "neutral" };
}

export function buildRotationNodes(industries: IndustryRow[], breadthRatio10 = 1): RotationNode[] {
  const active = industries.filter((r) => !r.excluded && r.rank_h > 0);

  const scored = active.map((row) => {
    const rs_score = rsFromRank(row.rank_h);
    const rs_3m = rsFromRank(row.rank_q);
    const rs_1m = rsFromRank(row.rank_m);
    const delta_1w = rsDelta1W(row);
    const rs_velocity = rsVelocity1M(row);
    const quadrant = classifyQuadrant3m1m(rs_3m, rs_1m);
    const trend = computeTrendState(row, breadthRatio10);
    return {
      industry_key: row.industry_key,
      name: row.name,
      rs_score,
      rs_3m,
      rs_1m,
      delta_1w,
      rs_velocity,
      quadrant,
      isAlpha: false,
      finviz_url: row.finviz_url,
      stock_picks: row.stock_picks || [],
      trendState: trend.trendState,
      trendTone: trend.trendTone,
    };
  });

  const top6mKeys = new Set(
    [...scored].sort((a, b) => b.rs_score - a.rs_score).slice(0, 10).map((x) => x.industry_key),
  );
  const top3mKeys = new Set(
    [...scored].sort((a, b) => b.rs_3m - a.rs_3m).slice(0, 10).map((x) => x.industry_key),
  );
  const top1mKeys = new Set(
    [...scored].sort((a, b) => b.rs_1m - a.rs_1m).slice(0, 10).map((x) => x.industry_key),
  );
  const alphaKeys = new Set([...top6mKeys, ...top3mKeys, ...top1mKeys]);

  return scored.map((node) => ({
    ...node,
    isAlpha: alphaKeys.has(node.industry_key),
  }));
}

export function buildAlphaRotationNodes(industries: IndustryRow[], breadthRatio10 = 1): RotationNode[] {
  return buildRotationNodes(industries, breadthRatio10).filter((n) => n.isAlpha);
}

export function filterAlphaRows(nodes: RotationNode[], filter: AlphaFilter): RotationNode[] {
  const alpha = nodes.filter((n) => n.isAlpha);

  const pool =
    filter === "ignition"
      ? alpha.filter((n) => n.quadrant === "ignition" || n.trendState === "Momentum Ignition")
      : filter === "oversold"
        ? alpha.filter((n) => n.rs_score < 55 && n.delta_1w > 0)
        : filter === "pullback"
          ? alpha.filter(
              (n) =>
                n.trendTone === "pullback" ||
                n.quadrant === "weakening" ||
                n.trendState === "Constructive Pullback",
            )
          : alpha;

  return pool
    .sort((a, b) => {
      if (filter === "ignition") return b.delta_1w - a.delta_1w;
      if (filter === "pullback") return b.rs_3m - a.rs_3m;
      if (filter === "oversold") return b.delta_1w - a.delta_1w;
      return b.delta_1w + b.rs_1m * 0.02 - (a.delta_1w + a.rs_1m * 0.02);
    })
    .slice(0, 12);
}

export function groupByQuadrant(nodes: RotationNode[]) {
  const groups: Record<Quadrant, RotationNode[]> = {
    leaders: [],
    ignition: [],
    weakening: [],
    lagging: [],
  };
  for (const n of nodes) {
    groups[n.quadrant].push(n);
  }
  for (const key of Object.keys(groups) as Quadrant[]) {
    groups[key].sort((a, b) => b.delta_1w + b.rs_1m * 0.01 - (a.delta_1w + a.rs_1m * 0.01));
  }
  return groups;
}
