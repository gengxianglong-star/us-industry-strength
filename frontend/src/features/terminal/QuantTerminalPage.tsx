import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Activity, RefreshCw } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";
import { IndustryRotationMap } from "../strong/components/IndustryRotationMap";
import type { AlphaFilter } from "../../lib/rotationLogic";
import type { TrendTone } from "../../lib/rotationLogic";
import "../../styles/cockpit.css";
import { calculateConfluenceScore, deriveMarketRegime, matrixCellStyle, type BreadthRow } from "./terminalRegime";
import { useQuantTerminal } from "./useQuantTerminal";

const TONE_STYLES = {
  cyan: { banner: "border-cyan-900/60 bg-cyan-950/10", title: "text-cyan-400", tag: "bg-cyan-600", glow: "drop-shadow-[0_0_8px_rgba(34,211,238,0.35)]" },
  emerald: { banner: "border-emerald-900/60 bg-emerald-950/10", title: "text-emerald-400", tag: "bg-emerald-600", glow: "" },
  rose: { banner: "border-rose-900/60 bg-rose-950/20", title: "text-rose-400", tag: "bg-rose-600", glow: "drop-shadow-[0_0_8px_rgba(244,63,94,0.35)]" },
  amber: { banner: "border-amber-900/60 bg-amber-950/10", title: "text-amber-400", tag: "bg-amber-600", glow: "" },
} as const;

function trendBadgeClass(tone: TrendTone) {
  if (tone === "expansion" || tone === "reversion") return "bg-emerald-950 text-emerald-400 border-emerald-800";
  if (tone === "pullback") return "bg-amber-950 text-amber-400 border-amber-800";
  if (tone === "bear") return "bg-rose-950 text-rose-400 border-rose-800";
  return "bg-slate-800 text-slate-400 border-slate-700";
}

function MatrixGrid({
  rows,
  field,
  color,
  label,
}: {
  rows: BreadthRow[];
  field: "c1_num" | "c2_num";
  color: "emerald" | "rose";
  label: string;
}) {
  const chronological = useMemo(() => [...rows].reverse().slice(-60), [rows]);
  const series = useMemo(
    () => chronological.map((r) => +(r[field] ?? 0)),
    [chronological, field],
  );
  const rgb = color === "emerald" ? "16, 185, 129" : "244, 63, 94";
  const glowRgb = color === "emerald" ? "52, 211, 153" : "251, 113, 133";
  const newest = chronological[chronological.length - 1];

  return (
    <div>
      <div className="flex justify-between text-[9px] mb-1 font-mono uppercase">
        <span className={color === "emerald" ? "text-emerald-500 font-bold" : "text-rose-500 font-bold"}>{label}</span>
        <span className="text-slate-500">{chronological.length}d · hot ≥500</span>
      </div>
      <div className="grid grid-cols-12 gap-1 bg-black/30 p-2 rounded">
        {chronological.map((row, idx) => {
          const val = +(row[field] ?? 0);
          const isLatest = row === newest;
          const cell = matrixCellStyle(val, series, rgb);
          return (
            <div
              key={`${row.raw_date || row.date || idx}-${field}`}
              className={`aspect-square rounded-sm transition-transform hover:scale-125 hover:z-10 cursor-crosshair ${
                isLatest ? "ring-1 ring-cyan-500/60" : ""
              } ${cell.hot ? "ring-1 ring-white/70" : ""}`}
              style={{
                backgroundColor: cell.backgroundColor,
                boxShadow: cell.hot
                  ? `0 0 ${8 + cell.whiteMix * 10}px rgba(255, 255, 255, ${0.35 + cell.whiteMix * 0.45}), 0 0 6px rgba(${glowRgb}, 0.6)`
                  : undefined,
              }}
              title={`${row.raw_date || row.date || "—"}: ${val}`}
            />
          );
        })}
      </div>
      <div className="flex justify-between text-[8px] text-slate-600 mt-1 font-mono uppercase">
        <span>← older</span>
        <span>newer →</span>
      </div>
    </div>
  );
}

function ThrustPanel({ rows, ratio10, ratio5 }: { rows: BreadthRow[]; ratio10: number; ratio5: number }) {
  const series = useMemo(() => {
    const chronological = [...rows].reverse().slice(-20);
    return chronological.map((r, i) => ({
      i,
      ratio10: +(r.c4_num ?? 0),
      ratio5: +(r.c3_num ?? 0),
      date: r.raw_date || r.date || "",
    }));
  }, [rows]);

  return (
    <section className="bg-[#0d1117] border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
      <h2 className="text-xs font-black text-slate-400 uppercase tracking-widest">Thrust Monitor</h2>

      <div className="grid grid-cols-2 gap-3">
        <div
          className={`p-2 rounded-lg border flex justify-between items-center ${
            ratio10 > 2 ? "bg-amber-950/30 border-amber-500/40" : ratio10 < 0.5 ? "bg-cyan-950/30 border-cyan-500/40" : "bg-slate-950/40 border-slate-900"
          }`}
        >
          <div>
            <div className="text-[9px] text-slate-500 font-mono uppercase">10D Ratio</div>
            <span className={`text-base font-mono font-black ${ratio10 > 2 ? "text-amber-400" : ratio10 < 0.5 ? "text-cyan-400" : "text-slate-200"}`}>
              {ratio10.toFixed(2)}
            </span>
          </div>
          {ratio10 > 2 ? <span className="text-[8px] font-mono font-black bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded animate-pulse">THRUST</span> : null}
          {ratio10 < 0.5 ? <span className="text-[8px] font-mono font-black bg-cyan-500/20 text-cyan-400 px-1.5 py-0.5 rounded">BEAR</span> : null}
        </div>
        <div
          className={`p-2 rounded-lg border flex justify-between items-center ${
            ratio5 > 2 ? "bg-amber-950/30 border-amber-500/40" : ratio5 < 0.5 ? "bg-cyan-950/30 border-cyan-500/40" : "bg-slate-950/40 border-slate-900"
          }`}
        >
          <div>
            <div className="text-[9px] text-slate-500 font-mono uppercase">5D Ratio</div>
            <span className={`text-base font-mono font-black ${ratio5 > 2 ? "text-amber-400" : ratio5 < 0.5 ? "text-cyan-400" : "text-slate-200"}`}>
              {ratio5.toFixed(2)}
            </span>
          </div>
          {ratio5 > 2 ? <span className="text-[8px] font-mono font-black bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">FAST</span> : null}
        </div>
      </div>

      <div className="h-28 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#1e293b" vertical={false} />
            <XAxis dataKey="i" hide />
            <YAxis tick={{ fill: "#64748b", fontSize: 9 }} width={32} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #334155", fontSize: 10 }}
              labelFormatter={(_, payload) => payload?.[0]?.payload?.date || ""}
            />
            <Line type="monotone" dataKey="ratio10" stroke="#22d3ee" strokeWidth={2} dot={false} name="10D" />
            <Line type="monotone" dataKey="ratio5" stroke="#94a3b8" strokeWidth={1.5} dot={false} name="5D" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export function QuantTerminalPage() {
  const { breadth, snapshot, loading, error, reload, industries, ratio10, filterAlphaRows, confluenceMinScore } =
    useQuantTerminal();
  const latest: BreadthRow = breadth?.rows?.[0] || {};
  const regime = deriveMarketRegime(latest);
  const confluence = useMemo(
    () => calculateConfluenceScore(latest, breadth?.rows || [], confluenceMinScore),
    [latest, breadth?.rows, confluenceMinScore],
  );
  const tone = TONE_STYLES[regime.tone];

  const [filter, setFilter] = useState<AlphaFilter>(regime.filterDefault);
  useEffect(() => setFilter(regime.filterDefault), [regime.filterDefault, regime.kind]);

  const alphaRows = useMemo(() => filterAlphaRows(filter), [filter, filterAlphaRows]);

  const ratio5 = +(latest.c3_num ?? 0);
  const t2108 = +(latest.c14_num ?? 0);
  const up4 = +(latest.c1_num ?? 0);
  const dn4 = +(latest.c2_num ?? 0);
  const snapshotDate =
    latest.raw_date || latest.date || snapshot?.snapshot_date || breadth?.coverage?.last_date || "—";

  if (loading) {
    return (
      <AppShell title="Stockbee Quant Terminal" source="Preview · Breadth × Strong Industry linkage">
        <div className="cockpit-preview flex items-center justify-center min-h-[400px]">
          <div className="flex items-center gap-3 text-slate-500 font-mono text-sm">
            <Activity className="animate-spin" size={16} /> SYNCING STRATEGIC TERMINAL...
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Stockbee Quant Terminal" source="Breadth Matrix · Rotation Radar · Regime-Linked Alpha">
      <div className="cockpit-preview max-w-[1600px] mx-auto px-4 md:px-6 py-6 space-y-6 font-mono">
        {error ? (
          <div className="rounded-lg border border-rose-900/50 bg-rose-950/20 px-4 py-3 text-sm text-rose-400">{error}</div>
        ) : null}

        <header
          className={`flex flex-col md:flex-row items-center justify-between gap-4 p-4 rounded-xl border ${tone.banner} ${regime.pulse ? "animate-pulse" : ""}`}
        >
          <div className="flex items-center gap-6 flex-wrap">
            <div>
              <h1 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Market Regime</h1>
              <div className={`text-xl md:text-2xl font-black italic ${tone.title} ${tone.glow}`}>{regime.title}</div>
            </div>
            <div className="h-10 w-px bg-slate-800 hidden sm:block" />
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] text-slate-500">
              <span>10D: <b className="text-slate-200">{ratio10.toFixed(2)}</b></span>
              <span>5D: <b className="text-slate-200">{ratio5.toFixed(2)}</b></span>
              <span>T2108: <b className="text-slate-200">{t2108.toFixed(1)}%</b></span>
              <span>Up/Dn 4%: <b className="text-slate-200">{up4}/{dn4}</b></span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => reload()}
              className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-[10px] px-3 py-1.5 rounded border border-slate-700 text-slate-300 uppercase"
            >
              <RefreshCw size={12} /> Refresh
            </button>
            <div className={`text-xs font-black text-white px-6 py-1 ${tone.tag}`} style={{ clipPath: "polygon(8% 0, 100% 0, 92% 100%, 0 100%)" }}>
              {regime.tag}
            </div>
          </div>
        </header>

        <main className="grid grid-cols-1 xl:grid-cols-12 gap-6">
          <div className="xl:col-span-4 space-y-6">
            <section className="bg-[#0d1117] border border-slate-800 rounded-xl p-5 shadow-lg">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-xs font-black text-slate-400 uppercase tracking-widest">Breadth Intensity Matrix</h2>
                <span className="text-[9px] text-slate-500">{snapshotDate}</span>
              </div>
              {confluence.activated ? (
                <div
                  className="mb-4 flex justify-center"
                  title={confluence.reasons.join(" · ")}
                >
                  <span className="px-4 py-1.5 text-[10px] font-black tracking-[0.2em] uppercase text-emerald-50 bg-emerald-700 border border-emerald-500/60 rounded shadow-[0_0_14px_rgba(16,185,129,0.45)]">
                    [ THRUST CONFLUENCE ACTIVATED ]
                  </span>
                </div>
              ) : null}
              <div className="space-y-4">
                <MatrixGrid rows={breadth?.rows || []} field="c1_num" color="emerald" label="4% Up Clusters" />
                <MatrixGrid rows={breadth?.rows || []} field="c2_num" color="rose" label="4% Down Clusters" />
              </div>
              <p className="text-[10px] text-slate-400 mt-4 pt-4 border-t border-slate-800">
                <span className="text-amber-500 font-bold">INSIGHT:</span> {regime.insight}
              </p>
            </section>
            <ThrustPanel rows={breadth?.rows || []} ratio10={ratio10} ratio5={ratio5} />
          </div>

          <div className="xl:col-span-8 space-y-6">
            <div className="relative">
              <div className="absolute top-4 right-4 z-10">
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value as AlphaFilter)}
                  className="bg-slate-900 text-[10px] border border-slate-700 px-2 py-1 rounded text-slate-300 outline-none focus:border-cyan-800"
                >
                  <option value="momentum">Momentum Velocity</option>
                  <option value="ignition">Momentum Ignition (Q2)</option>
                  <option value="oversold">Mean Reversion / RSD</option>
                  <option value="pullback">Constructive Pullback</option>
                </select>
              </div>
              <IndustryRotationMap industries={industries} breadthRatio10={ratio10} />
            </div>

            <section className="bg-[#0d1117] border border-slate-800 rounded-xl overflow-hidden shadow-lg">
              <div className="px-4 py-2 border-b border-slate-800 flex justify-between items-center">
                <span className="text-[10px] font-black text-slate-400 uppercase">Dynamic Alpha List</span>
                <span className="text-[9px] text-slate-600">
                  {regime.filterDefault === filter ? "regime-linked" : "manual override"}
                </span>
              </div>
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="bg-slate-900 text-slate-500 font-bold border-b border-slate-800 uppercase tracking-tighter">
                    <th className="p-3">Industry</th>
                    <th className="p-3">6M RS</th>
                    <th className="p-3">1W Δ</th>
                    <th className="p-3">Trend State</th>
                    <th className="p-3 text-right">Focus</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {alphaRows.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-6 text-center text-slate-500">No matches for current filter.</td>
                    </tr>
                  ) : (
                    alphaRows.map((row) => (
                      <tr key={row.industry_key} className="hover:bg-slate-800/40 group">
                        <td className="p-3">
                          <a className="font-bold text-slate-200 group-hover:text-cyan-400" href={row.finviz_url} target="_blank" rel="noreferrer">
                            {row.name}
                          </a>
                          {row.stock_picks.length > 0 ? (
                            <div className="text-[9px] text-slate-500 truncate max-w-[200px]">{row.stock_picks.slice(0, 4).join(", ")}</div>
                          ) : null}
                        </td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <span>{row.rs_score}</span>
                            <div className="w-10 h-1 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full bg-emerald-500" style={{ width: `${row.rs_score}%` }} />
                            </div>
                          </div>
                        </td>
                        <td className={`p-3 ${row.delta_1w >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                          {row.delta_1w >= 0 ? "+" : ""}{row.delta_1w}
                        </td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${trendBadgeClass(row.trendTone)}`}>
                            {row.trendState.toUpperCase()}
                          </span>
                        </td>
                        <td className="p-3 text-right">
                          <a
                            className="text-cyan-400 hover:underline text-[10px]"
                            href={row.stock_picks[0] ? `https://finviz.com/quote.ashx?t=${encodeURIComponent(row.stock_picks[0])}` : row.finviz_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {row.stock_picks[0] || "GROUP"} →
                          </a>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </section>
          </div>
        </main>
      </div>
    </AppShell>
  );
}
