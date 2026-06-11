import { WatchlistFinvizChart } from "./WatchlistLightweightChart";
import {
  computeLongTrend,
  computeShortTrend,
  finvizQuoteUrl,
  getTopStrongIndustries,
  normalizeTrendLabel,
  pct,
  perfScales,
  rankHeat,
  type IndustryRow,
  type RsPayload,
  type SnapshotPayload,
  type WatchlistRow,
} from "../../../lib/industry";

function watchlistIndustryLabel(
  row: WatchlistRow,
  industryNames?: Map<string, string>,
) {
  const direct = (row.industry_name || row.name || "").trim();
  if (direct) return direct;
  return (row.industries || [])
    .map((key) => industryNames?.get(key) || key)
    .filter(Boolean)
    .join(" · ");
}

export function WatchlistFinvizSymbolLink({ symbol }: { symbol: string }) {
  return (
    <a
      href={finvizQuoteUrl(symbol)}
      target="_blank"
      rel="noreferrer"
      className="font-mono font-black text-cyan-400 text-sm hover:text-cyan-300 hover:underline"
      title="Open Finviz quote & chart"
    >
      {symbol}
    </a>
  );
}

function trendPillClass(text: string) {
  const t = normalizeTrendLabel(text);
  if (t === "A↑") return "bg-emerald-950/50 text-emerald-400 border-emerald-800/60";
  if (t === "A↓") return "bg-emerald-950/30 text-emerald-500/80 border-emerald-900/40";
  if (t === "PB↑") return "bg-cyan-950/40 text-cyan-400 border-cyan-900/50";
  if (t === "PB↓") return "bg-amber-950/40 text-amber-400 border-amber-900/50";
  if (t === "A") return "bg-emerald-950/40 text-emerald-400 border-emerald-900/50";
  if (t === "PB") return "bg-slate-800 text-slate-400 border-slate-700";
  return "bg-slate-900 text-slate-500 border-slate-800";
}

export function TrendBadge({ text }: { text: string }) {
  if (!text) return <span className="text-slate-600 font-mono text-[10px]">—</span>;
  const label = normalizeTrendLabel(text);
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-mono font-bold tracking-wide ${trendPillClass(label)}`}
    >
      {label}
    </span>
  );
}

export function PerfMicroBar({ value, maxAbs }: { value: number; maxAbs: number }) {
  const v = Number(value);
  if (!Number.isFinite(v)) {
    return <span className="text-slate-600 font-mono text-[10px]">—</span>;
  }
  const scale = Math.max(Number(maxAbs) || 0.01, 0.01);
  const widthPct = Math.min(50, (Math.abs(v) / scale) * 50);
  const isPos = v >= 0;

  return (
    <div className="flex items-center gap-1.5 min-w-[92px]">
      <div className="relative flex-1 h-2 bg-slate-950 rounded-sm overflow-hidden border border-slate-800/80">
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-600/80 z-10" aria-hidden />
        {isPos ? (
          <div
            className="absolute left-1/2 top-0 bottom-0 bg-emerald-500/85 rounded-r-sm"
            style={{ width: `${widthPct}%` }}
          />
        ) : (
          <div
            className="absolute right-1/2 top-0 bottom-0 bg-rose-500/85 rounded-l-sm"
            style={{ width: `${widthPct}%` }}
          />
        )}
      </div>
      <span
        className={`font-mono text-[10px] tabular-nums w-[52px] text-right shrink-0 ${
          isPos ? "text-emerald-400" : "text-rose-400"
        }`}
      >
        {pct(v)}
      </span>
    </div>
  );
}

function rankSquareClass(rank: number) {
  if (rank <= 10) return "bg-emerald-500 border-emerald-400 text-slate-950 font-black";
  if (rank <= 20) return "bg-emerald-950 border-emerald-700 text-emerald-300";
  if (rank >= 100) return "bg-rose-950 border-rose-800 text-rose-400";
  return "bg-slate-800 border-slate-700 text-slate-400";
}

export function RankCompactRow({ row }: { row: IndustryRow }) {
  const items: [string, number][] = [
    ["W", row.rank_w],
    ["M", row.rank_m],
    ["Q", row.rank_q],
    ["H", row.rank_h],
    ["Y", row.rank_y],
  ];
  return (
    <span
      className="inline-flex rounded overflow-hidden border border-slate-700"
      aria-label={`Rank W${row.rank_w} M${row.rank_m} Q${row.rank_q} H${row.rank_h} Y${row.rank_y}`}
    >
      {items.map(([label, rank], idx) => (
        <span
          key={label}
          className={`flex flex-col items-center justify-center px-1 py-0.5 min-w-[28px] border-slate-700 font-mono text-[9px] leading-none ${rankSquareClass(rank)} ${idx > 0 ? "border-l" : ""}`}
          title={`${label} rank ${rank} — lower is stronger`}
        >
          <span className="opacity-70 text-[8px]">{label}</span>
          <span className="text-[10px]">{rank}</span>
        </span>
      ))}
    </span>
  );
}

export function CoreIndustryTable({ snapshot }: { snapshot: SnapshotPayload | null }) {
  const top = snapshot ? getTopStrongIndustries(snapshot) : [];
  const scales = perfScales(top);

  if (!top.length) {
    return (
      <tbody>
        <tr>
          <td colSpan={11} className="p-6 text-center text-slate-500 font-mono text-xs">
            No snapshot yet — daily run in progress…
          </td>
        </tr>
      </tbody>
    );
  }

  return (
    <tbody>
      {top.map((row) => (
        <tr
          key={row.industry_key}
          data-key={row.industry_key}
          className="border-b border-slate-800/60 hover:bg-slate-900/40 transition-colors"
        >
          <td className="p-3 font-semibold text-slate-200">
            <a
              className="text-cyan-400 hover:text-cyan-300 transition-colors"
              href={row.finviz_url}
              target="_blank"
              rel="noreferrer"
            >
              {row.name}
            </a>
          </td>
          <td className="p-3 text-right font-mono text-slate-400">{row.stocks}</td>
          <td className="p-3 text-right font-mono font-bold text-amber-400/90">
            {row.score.toFixed(3)}
          </td>
          <td className="p-3">
            <PerfMicroBar value={row.perf_w} maxAbs={scales.perf_w} />
          </td>
          <td className="p-3">
            <PerfMicroBar value={row.perf_m} maxAbs={scales.perf_m} />
          </td>
          <td className="p-3">
            <PerfMicroBar value={row.perf_q} maxAbs={scales.perf_q} />
          </td>
          <td className="p-3">
            <PerfMicroBar value={row.perf_h} maxAbs={scales.perf_h} />
          </td>
          <td className="p-3">
            <PerfMicroBar value={row.perf_y} maxAbs={scales.perf_y} />
          </td>
          <td className="p-3 text-center">
            <RankCompactRow row={row} />
          </td>
          <td className="p-3 text-center">
            <TrendBadge text={computeShortTrend(row)} />
          </td>
          <td className="p-3 text-center">
            <TrendBadge text={computeLongTrend(row)} />
          </td>
        </tr>
      ))}
    </tbody>
  );
}

export function WatchlistChartGrid({
  watchlist,
  industryNames,
}: {
  watchlist: RsPayload["watchlist"];
  industryNames?: Map<string, string>;
}) {
  if (!watchlist.length) {
    return (
      <p className="text-xs text-slate-500 font-mono py-4 text-center">
        Charts appear after the daily watchlist is built.
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 max-h-[78vh] overflow-y-auto pr-1">
      {watchlist.map((row) => {
        const industry = watchlistIndustryLabel(row, industryNames);
        return (
          <article
            key={row.symbol}
            className="bg-black border border-slate-800 rounded-lg overflow-hidden hover:border-cyan-500/40 hover:shadow-[0_0_12px_rgba(34,211,238,0.08)] transition-all"
          >
            <div className="px-2.5 py-1.5 border-b border-slate-800/80 bg-slate-950/80">
              <div className="flex justify-between items-center gap-2">
                <div className="flex flex-col min-w-0">
                  <div className="flex items-center gap-2">
                    <WatchlistFinvizSymbolLink symbol={row.symbol} />
                    {industry ? (
                      <span className="text-[10px] font-mono text-slate-400 border border-slate-700 px-1.5 py-0.5 rounded truncate max-w-[140px]">
                        {industry}
                      </span>
                    ) : null}
                  </div>
                  {row.catalyst?.tag && (
                    <span
                      className="cursor-help mt-0.5 self-start text-[10px] font-bold bg-emerald-900/40 text-emerald-400 px-1.5 py-0.5 rounded border border-emerald-800/50 hover:bg-emerald-800/60 transition-colors"
                      title={row.catalyst.headlines?.join(' • ') ?? row.catalyst.tag}
                    >
                      ⚡ {row.catalyst.tag}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-[10px] font-mono shrink-0">
                  <span
                    className={`font-bold ${rankDeltaClass(row.rank_w_delta)}`}
                    title="1W rank Δ"
                  >
                    {fmtRankDelta(row.rank_w_delta)}
                  </span>
                  <span className="text-slate-500">RS {Number(row.rs_score).toFixed(2)}</span>
                </div>
              </div>
            </div>
            <a
              href={finvizQuoteUrl(row.symbol)}
              target="_blank"
              rel="noreferrer"
              className="block"
              title="Open Finviz quote & chart"
            >
              <WatchlistFinvizChart symbol={row.symbol} />
              <div className="px-2 py-1 border-t border-slate-900 text-[9px] font-mono text-slate-600">
                Finviz · click for full chart
              </div>
            </a>
          </article>
        );
      })}
    </div>
  );
}

export function fmtPerf(v: unknown) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

export function fmtRankDelta(v: unknown) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  const n = Number(v);
  if (n === 0) return "0";
  return n > 0 ? `+${n}` : String(n);
}

export function rankDeltaClass(v: unknown) {
  if (v == null || !Number.isFinite(Number(v))) return "text-slate-500";
  const n = Number(v);
  if (n > 0) return "text-emerald-400";
  if (n < 0) return "text-rose-400";
  return "text-slate-400";
}

export function rankHeatClass(rank: number) {
  return rankHeat(rank);
}

export function terminalPerfClass(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "text-slate-500";
  return n >= 0 ? "text-emerald-400" : "text-rose-400";
}

export function terminalRankClass(rank: number) {
  if (rank <= 20) return "text-emerald-400 font-bold";
  if (rank >= 100) return "text-rose-400";
  return "text-slate-400";
}
