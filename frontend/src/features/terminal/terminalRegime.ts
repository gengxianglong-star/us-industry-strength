export type BreadthRow = {
  date?: string;
  raw_date?: string;
  c1_num?: number;
  c2_num?: number;
  c3_num?: number;
  c4_num?: number;
  c5_num?: number;
  c6_num?: number;
  c14_num?: number;
};

export type RegimeKind =
  | "bull_thrust"
  | "bear_thrust"
  | "overbought"
  | "oversold"
  | "neutral";

export type MarketRegime = {
  kind: RegimeKind;
  title: string;
  tag: string;
  tone: "cyan" | "emerald" | "rose" | "amber";
  pulse: boolean;
  insight: string;
  filterDefault: "momentum" | "ignition" | "oversold" | "pullback";
};

export function deriveMarketRegime(latest: BreadthRow): MarketRegime {
  const ratio10 = +(latest.c4_num ?? 0);
  const ratio5 = +(latest.c3_num ?? 0);
  const t2108 = +(latest.c14_num ?? 0);
  const up4 = +(latest.c1_num ?? 0);
  const dn4 = +(latest.c2_num ?? 0);
  const up25q = +(latest.c5_num ?? 0);
  const dn25q = +(latest.c6_num ?? 0);

  if (dn4 >= 500) {
    return {
      kind: "oversold",
      title: "CAPITULATION / PANIC SELLING",
      tag: "RSD DIVERGENCE SCAN",
      tone: "emerald",
      pulse: true,
      filterDefault: "oversold",
      insight: `Down 4% = ${dn4} (capitulation zone). Hunt industries drifting top-right in rotation — relative strength divergence candidates for the next cycle.`,
    };
  }

  if (t2108 >= 80 || (t2108 >= 60 && ratio10 >= 2.0 && dn4 < 100)) {
    return {
      kind: "overbought",
      title: "CLIMAX OVERBOUGHT / CAUTION",
      tag: "PROTECT PROFITS",
      tone: "rose",
      pulse: true,
      filterDefault: "pullback",
      insight: `T2108 ${t2108.toFixed(1)}% with 10D ratio ${ratio10.toFixed(2)} — breadth is extended. Favor constructive pullbacks over fresh breakouts; watch for 4% down clusters > 300.`,
    };
  }

  if (t2108 <= 20 || ratio10 <= 0.5) {
    return {
      kind: "oversold",
      title: "EXTREME OVERSOLD / REVERSION WATCH",
      tag: "MEAN REVERSION SCAN",
      tone: "emerald",
      pulse: t2108 <= 20,
      filterDefault: "oversold",
      insight: `T2108 ${t2108.toFixed(1)}%, 10D ratio ${ratio10.toFixed(2)} — capitulation risk elevated. Scan for low RS industries with positive 1M velocity (RSD divergence).`,
    };
  }

  if (ratio10 >= 2.0 && ratio5 >= 1.2 && up25q >= dn25q) {
    return {
      kind: "bull_thrust",
      title: "CONFIRMED BULL THRUST",
      tag: "AGGRESSIVE RISK-ON",
      tone: "cyan",
      pulse: false,
      filterDefault: "ignition",
      insight: `Thrust intact: 10D ${ratio10.toFixed(2)}, 5D ${ratio5.toFixed(2)}. Pin Ignition quadrant (weak RS + steep velocity) — new leaders emerge here before Top 10 RS lists.`,
    };
  }

  if (ratio10 <= 0.5 || (up25q < dn25q && dn4 > up4)) {
    return {
      kind: "bear_thrust",
      title: "BEAR THRUST / DEFENSIVE",
      tag: "REDUCE BETA",
      tone: "rose",
      pulse: false,
      filterDefault: "oversold",
      insight: `Bearish breadth: 10D ratio ${ratio10.toFixed(2)}, quarter up ${up25q} vs down ${dn25q}. Avoid extended leaders; relative-strength laggards with velocity may be tactical only.`,
    };
  }

  return {
    kind: "neutral",
    title: "RANGE / SELECTIVE ALPHA",
    tag: "STOCK PICKERS MARKET",
    tone: "amber",
    pulse: false,
    filterDefault: "momentum",
    insight: `Mixed regime: 10D ${ratio10.toFixed(2)}, T2108 ${t2108.toFixed(1)}%. Use rotation scatter — chase top-right, avoid bottom-right stall zones.`,
  };
}

export function matrixOpacity(value: number, max: number) {
  if (!Number.isFinite(value) || value <= 0) return 0.08;
  return Math.min(0.15 + value / Math.max(max, 1), 1);
}
