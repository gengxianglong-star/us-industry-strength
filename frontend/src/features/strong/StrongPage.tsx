import { AppShell } from "../../components/layout/AppShell";
import { IS_READONLY } from "../../lib/api";
import { getTopStrongIndustries } from "../../lib/industry";
import { ConfigPanel } from "./components/ConfigPanel";
import {
  CoreIndustryTable,
  fmtPerf,
  terminalPerfClass,
  terminalRankClass,
  WatchlistChartGrid,
} from "./components/StrongTables";
import { useStrongPage } from "./useStrongPage";
import {
  Target,
  ListFilter,
  Activity,
  Database,
  AlertCircle,
  Crosshair,
  TrendingUp,
  Layers,
} from "lucide-react";
import "../../styles/cockpit.css";

function formatAdaptiveStop(reason?: string | null) {
  const labels: Record<string, string> = {
    min_recovered: "min recovered",
    no_retryable: "complete",
    stall: "stalled",
    max_passes: "max passes",
  };
  if (!reason) return "—";
  return labels[reason] || reason;
}

const panelSummaryClass =
  "p-4 bg-slate-900/40 hover:bg-slate-800/40 transition-colors font-black text-sm text-slate-300 uppercase tracking-widest flex items-center justify-between list-none cursor-pointer";

export function StrongPage() {
  const {
    snapshot,
    rsPayload,
    rsStatus,
    rsStatusError,
    search,
    setSearch,
    topListCount,
    watchlist,
    filteredIndustries,
    NEW_STOCK_COHORT_LABEL,
  } = useStrongPage();

  const meta = snapshot?.rs_meta || rsPayload?.rs_meta;
  const newStockRsCount =
    (meta?.new_stock_m_count ?? 0) +
    (meta?.new_stock_q_count ?? 0) +
    (meta?.new_stock_h_count ?? 0) +
    (meta?.new_stock_3q_count ?? 0);
  const covered = (meta?.computed_count ?? 0) + newStockRsCount;
  const topIndustries = snapshot ? getTopStrongIndustries(snapshot) : [];

  return (
    <AppShell
      title="Strong Industry Terminal"
      source="Source: Finviz Industry Groups · Yahoo RS · Finviz Screener"
    >
      <div className="cockpit-preview max-w-[1600px] mx-auto px-4 md:px-6 py-6 space-y-6">
        {/* Hero Dashboard */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div
            className={`md:col-span-1 rounded-xl border p-5 flex flex-col justify-between shadow-lg ${
              rsStatusError ? "bg-rose-950/20 border-rose-900/50" : "bg-[#0b0f19] border-slate-800"
            }`}
          >
            <div>
              <h3 className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-1 flex items-center gap-1.5">
                <Activity size={12} className={rsStatusError ? "text-rose-500" : "text-cyan-500"} />
                Engine Status
              </h3>
              <div className="text-sm font-bold mt-2">
                <span className={rsStatusError ? "text-rose-400" : "text-emerald-400"}>
                  {rsStatus || "Waiting for signal..."}
                </span>
              </div>
            </div>
            <div className="text-[10px] text-slate-500 font-mono mt-4 pt-4 border-t border-slate-800/60">
              Snapshot: {snapshot?.snapshot_date || "—"}
            </div>
          </div>

          <div className="md:col-span-3 grid grid-cols-1 sm:grid-cols-3 gap-4 bg-[#0b0f19] rounded-xl border border-slate-800 p-5 shadow-lg">
            <div className="flex flex-col justify-center">
              <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                <Target size={12} className="text-amber-500" /> Focus Target
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-black font-mono tracking-tighter text-slate-200">
                  {topIndustries.length || topListCount}
                </span>
                <span className="text-xs font-bold text-slate-500">Top Groups</span>
              </div>
            </div>

            <div className="flex flex-col justify-center sm:border-l border-slate-800 sm:pl-6">
              <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                <Crosshair size={12} className="text-cyan-500" /> Final Watchlist
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-black font-mono tracking-tighter text-cyan-400">
                  {watchlist.length}
                </span>
                <span className="text-xs font-bold text-slate-500">Candidates</span>
              </div>
            </div>

            <div className="flex flex-col justify-center sm:border-l border-slate-800 sm:pl-6">
              <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                <Database size={12} className="text-indigo-400" /> RS Universe
              </span>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-black font-mono tracking-tighter text-slate-300">
                  {covered.toLocaleString()}
                </span>
                <span className="text-xs font-bold text-slate-500">Equities</span>
              </div>
            </div>
          </div>
        </div>

        {/* Top Strong Industries */}
        <section className="bg-[#0b0f19] border border-slate-800 rounded-xl shadow-lg overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-[#090e1a]">
            <div>
              <h2 className="text-sm font-black text-slate-200 uppercase tracking-widest flex items-center gap-2">
                <TrendingUp size={16} className="text-emerald-500" /> Top Strong Industries
              </h2>
              <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest mt-1">
                Ranked by Multi-Timeframe Momentum Engine
              </p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs whitespace-nowrap">
              <thead>
                <tr className="bg-slate-900/50 text-slate-400 border-b border-slate-800 font-mono text-[10px] uppercase tracking-wider">
                  <th className="p-3 font-semibold">Industry</th>
                  <th className="p-3 font-semibold text-right">Stocks</th>
                  <th className="p-3 font-semibold text-right">Score</th>
                  <th className="p-3 font-semibold">1W</th>
                  <th className="p-3 font-semibold">1M</th>
                  <th className="p-3 font-semibold">3M</th>
                  <th className="p-3 font-semibold">6M</th>
                  <th className="p-3 font-semibold">1Y</th>
                  <th className="p-3 font-semibold text-center" title="W/M/Q/H/Y rank">
                    Rank Hist
                  </th>
                  <th className="p-3 font-semibold text-center">Short</th>
                  <th className="p-3 font-semibold text-center">Long</th>
                </tr>
              </thead>
              <CoreIndustryTable snapshot={snapshot} />
            </table>
          </div>
        </section>

        {/* Watchlist */}
        <section className="bg-[#0b0f19] border border-slate-800 rounded-xl shadow-lg p-5">
          <div className="mb-4">
            <h2 className="text-sm font-black text-slate-200 uppercase tracking-widest flex items-center gap-2">
              <Target size={16} className="text-rose-500" /> Final Watchlist Setup
            </h2>
            <p className="text-[10px] font-mono text-slate-500 uppercase mt-1">
              Equities clearing RS threshold + Finviz momentum screen.
            </p>
          </div>
          <WatchlistChartGrid watchlist={watchlist} />
        </section>

        {/* Evidence B */}
        <details className="group bg-[#0b0f19] border border-slate-800 rounded-xl shadow-lg overflow-hidden" id="strongCardsPanel">
          <summary className={panelSummaryClass}>
            <span className="flex items-center gap-2">
              <ListFilter size={16} className="text-amber-500" /> Finviz Screen Hits by Industry
            </span>
            <span className="text-[10px] text-slate-500 font-mono group-open:hidden">Click to expand</span>
          </summary>
          <div className="p-5 border-t border-slate-800 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {topIndustries.map((row, idx) => (
              <article
                key={row.industry_key}
                className="bg-slate-900/50 border border-slate-800 rounded-lg p-4 flex flex-col hover:border-slate-600 transition-colors min-h-[120px]"
              >
                <header className="flex justify-between items-start mb-3 gap-2">
                  <div className="min-w-0">
                    <span className="text-[10px] font-black text-slate-500 font-mono bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800 mr-2">
                      #{idx + 1}
                    </span>
                    <a
                      className="text-sm font-bold text-cyan-400 hover:text-cyan-300"
                      href={row.finviz_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {row.name}
                    </a>
                  </div>
                  <span className="text-[10px] font-mono text-emerald-500 bg-emerald-950/30 px-2 py-0.5 rounded-full border border-emerald-900/50 shrink-0">
                    {(row.stock_picks || []).length} Hits
                  </span>
                </header>
                {row.stock_picks_error ? (
                  <p className="text-xs text-rose-500 flex items-center gap-1 mt-auto">
                    <AlertCircle size={12} /> {row.stock_picks_error}
                  </p>
                ) : (row.stock_picks || []).length === 0 ? (
                  <p className="text-xs text-slate-500 mt-auto">
                    No hits{" "}
                    {row.stock_screener_url ? (
                      <a
                        className="text-indigo-400 hover:underline ml-1"
                        href={row.stock_screener_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        (Open Screener)
                      </a>
                    ) : null}
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5 mt-auto">
                    {(row.stock_picks || []).map((t) => (
                      <a
                        key={t}
                        className="text-xs font-mono font-bold text-slate-300 bg-slate-800 hover:bg-slate-700 px-2 py-1 rounded transition-colors"
                        href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(t)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {t}
                      </a>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        </details>

        {/* Evidence A: RS */}
        <details className="group bg-[#0b0f19] border border-slate-800 rounded-xl shadow-lg overflow-hidden" id="rsPanel">
          <summary className={panelSummaryClass}>
            <span className="flex items-center gap-2">
              <Database size={16} className="text-indigo-500" /> Evidence A: Raw Stock RS Data
            </span>
            <span className="text-[10px] text-slate-500 font-mono group-open:hidden">Expand</span>
          </summary>
          <div className="p-4 border-t border-slate-800 space-y-5">
            <div className="flex flex-wrap gap-2 text-[10px] font-mono uppercase tracking-wide">
              {meta ? (
                <>
                  <span className="px-2 py-1 rounded border border-slate-800 bg-slate-900/50 text-slate-400">
                    Universe {meta.universe_count}
                  </span>
                  <span className="px-2 py-1 rounded border border-slate-800 bg-slate-900/50 text-slate-400">
                    Covered {covered}
                  </span>
                  <span className="px-2 py-1 rounded border border-slate-800 bg-slate-900/50 text-slate-400">
                    Main RS {meta.computed_count}
                  </span>
                  <span className="px-2 py-1 rounded border border-slate-800 bg-slate-900/50 text-slate-400">
                    New IPO RS {newStockRsCount}
                  </span>
                  <span className="px-2 py-1 rounded border border-slate-800 bg-slate-900/50 text-slate-400">
                    No bars {meta.no_bars_count}
                  </span>
                  {Number(meta.adaptive_passes) > 0 ? (
                    <span className="px-2 py-1 rounded border border-cyan-900/50 bg-cyan-950/20 text-cyan-400">
                      Adaptive: {meta.adaptive_passes} passes · +{meta.adaptive_recovered_total ?? 0} ·{" "}
                      {formatAdaptiveStop(meta.adaptive_stop_reason)}
                    </span>
                  ) : null}
                </>
              ) : (
                <span className="text-slate-500">Coverage: waiting on RS run</span>
              )}
            </div>
            <p className="text-[10px] font-mono text-slate-600">Prices: Yahoo adj. close</p>

            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <h3 className="text-[10px] font-mono text-slate-500 uppercase tracking-widest p-3 border-b border-slate-800 bg-slate-900/30">
                RS Top
              </h3>
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800 bg-slate-900/20 text-[10px] uppercase">
                    <th className="p-2 text-left">Symbol</th>
                    <th className="p-2 text-right">Score</th>
                    <th className="p-2">Tier</th>
                    <th className="p-2 text-right">1W</th>
                    <th className="p-2 text-right">1M</th>
                    <th className="p-2 text-right">3M</th>
                    <th className="p-2 text-right">6M</th>
                    <th className="p-2 text-right">1Y</th>
                    <th className="p-2">Rank W/M/Q/H/Y</th>
                  </tr>
                </thead>
                <tbody>
                  {(rsPayload?.rows || []).length === 0 ? (
                    <tr>
                      <td colSpan={9} className="p-4 text-slate-500 text-center">
                        No RS data yet — fills in after the daily run.
                      </td>
                    </tr>
                  ) : (
                    rsPayload!.rows.map((row) => (
                      <tr key={String(row.symbol)} className="border-b border-slate-800/50 hover:bg-slate-900/30">
                        <td className="p-2">
                          <a
                            className="text-cyan-400 hover:text-cyan-300"
                            href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(String(row.symbol))}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {String(row.symbol)}
                          </a>
                        </td>
                        <td className="p-2 text-right text-slate-300">{Number(row.rs_score).toFixed(3)}</td>
                        <td className="p-2 text-slate-400">{String(row.tier)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_w)}`}>{fmtPerf(row.perf_w)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_m)}`}>{fmtPerf(row.perf_m)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_q)}`}>{fmtPerf(row.perf_q)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_h)}`}>{fmtPerf(row.perf_h)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_y)}`}>{fmtPerf(row.perf_y)}</td>
                        <td className="p-2 text-slate-500">
                          {[row.rank_w, row.rank_m, row.rank_q, row.rank_h, row.rank_y]
                            .map((r) => (r == null ? "—" : String(r)))
                            .join("/")}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <h3 className="text-[10px] font-mono text-slate-500 uppercase tracking-widest p-3 border-b border-slate-800 bg-slate-900/30">
                New Stock RS Leaderboard
              </h3>
              <p className="text-[10px] text-slate-600 p-3 border-b border-slate-800">
                M/Q/H/3Q cohorts (22–259 bars). Top 10% per cohort can cross with Top Finviz picks.
              </p>
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800 bg-slate-900/20 text-[10px] uppercase">
                    <th className="p-2 text-left">Cohort</th>
                    <th className="p-2 text-left">Symbol</th>
                    <th className="p-2 text-right">Bars</th>
                    <th className="p-2 text-right">Score</th>
                    <th className="p-2">Tier</th>
                    <th className="p-2 text-right">1W</th>
                    <th className="p-2 text-right">1M</th>
                    <th className="p-2 text-right">3M</th>
                    <th className="p-2 text-right">6M</th>
                    <th className="p-2 text-right">3Q</th>
                  </tr>
                </thead>
                <tbody>
                  {(rsPayload?.new_stock_leaderboard || []).length === 0 ? (
                    <tr>
                      <td colSpan={9} className="p-4 text-slate-500 text-center">
                        No new-issue RS leaderboard yet
                      </td>
                    </tr>
                  ) : (
                    rsPayload!.new_stock_leaderboard.map((row, idx) => (
                      <tr key={`${row.symbol}-${idx}`} className="border-b border-slate-800/50 hover:bg-slate-900/30">
                        <td className="p-2 text-slate-400">
                          {NEW_STOCK_COHORT_LABEL[String(row.cohort)] || String(row.cohort)}
                        </td>
                        <td className="p-2">
                          <a
                            className="text-cyan-400 hover:text-cyan-300"
                            href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(String(row.symbol))}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {String(row.symbol)}
                          </a>
                        </td>
                        <td className="p-2 text-right text-slate-500">
                          {row.bar_count != null ? String(row.bar_count) : "—"}
                        </td>
                        <td className="p-2 text-right text-slate-300">{Number(row.rs_score).toFixed(3)}</td>
                        <td className="p-2 text-slate-400">{String(row.tier)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_w)}`}>{fmtPerf(row.perf_w)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_m)}`}>{fmtPerf(row.perf_m)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_q)}`}>{fmtPerf(row.perf_q)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_h)}`}>{fmtPerf(row.perf_h)}</td>
                        <td className={`p-2 text-right ${terminalPerfClass(row.perf_tq)}`}>{fmtPerf(row.perf_tq)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </details>

        {/* All Industries Reference */}
        <details className="group bg-[#0b0f19] border border-slate-800 rounded-xl shadow-lg overflow-hidden">
          <summary className={panelSummaryClass}>
            <span className="flex items-center gap-2">
              <Layers size={16} className="text-slate-400" /> Reference: All Industries (Rank Heatmap)
            </span>
            <span className="text-[10px] text-slate-500 font-mono group-open:hidden">Expand</span>
          </summary>
          <div className="p-4 border-t border-slate-800 space-y-4">
            <p className="text-[10px] font-mono text-slate-600 uppercase">
              Full sector rank map — expand when you need backup groups.
            </p>
            <input
              id="searchInput"
              type="search"
              name="industry_search"
              placeholder="Search industry…"
              autoComplete="off"
              spellCheck={false}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full max-w-md bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono placeholder:text-slate-600 focus:outline-none focus:border-cyan-800"
            />
            <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-[420px] overflow-y-auto">
              <table className="w-full text-xs font-mono">
                <thead className="sticky top-0 z-10 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800 text-[10px] uppercase">
                    <th className="p-2 text-left">Industry</th>
                    <th className="p-2 text-right">Stocks</th>
                    <th className="p-2 text-right">Score</th>
                    <th className="p-2 text-right">W</th>
                    <th className="p-2 text-right">M</th>
                    <th className="p-2 text-right">Q</th>
                    <th className="p-2 text-right">H</th>
                    <th className="p-2 text-right">Y</th>
                    <th className="p-2 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredIndustries.map((row) => {
                    const status = row.excluded
                      ? row.exclude_reason
                      : row.is_top_strong
                        ? `Top ${topListCount}`
                        : row.tier;
                    return (
                      <tr
                        key={row.industry_key}
                        data-key={row.industry_key}
                        className={`border-b border-slate-800/40 hover:bg-slate-900/30 ${row.excluded ? "opacity-50" : ""}`}
                      >
                        <td className="p-2 text-slate-300">{row.name}</td>
                        <td className="p-2 text-right text-slate-500">{row.stocks}</td>
                        <td className="p-2 text-right text-amber-400/80">
                          {row.excluded ? "—" : row.score.toFixed(3)}
                        </td>
                        <td className={`p-2 text-right ${terminalRankClass(row.rank_w)}`}>{row.rank_w}</td>
                        <td className={`p-2 text-right ${terminalRankClass(row.rank_m)}`}>{row.rank_m}</td>
                        <td className={`p-2 text-right ${terminalRankClass(row.rank_q)}`}>{row.rank_q}</td>
                        <td className={`p-2 text-right ${terminalRankClass(row.rank_h)}`}>{row.rank_h}</td>
                        <td className={`p-2 text-right ${terminalRankClass(row.rank_y)}`}>{row.rank_y}</td>
                        <td className="p-2 text-slate-500">{status}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </details>

        {!IS_READONLY ? <ConfigPanel /> : null}

        <footer className="text-[10px] font-mono text-slate-600 text-center pt-4 border-t border-slate-800/50">
          Data:{" "}
          <a
            className="text-cyan-600 hover:text-cyan-400"
            href="https://finviz.com/groups?g=industry&v=210&o=name"
            target="_blank"
            rel="noreferrer"
          >
            Finviz Industry Groups
          </a>{" "}
          (15 min delay) · Research only, not investment advice
        </footer>
      </div>
    </AppShell>
  );
}
