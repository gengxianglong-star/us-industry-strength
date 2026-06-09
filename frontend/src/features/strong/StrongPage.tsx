import { AppShell } from "../../components/layout/AppShell";
import {
  CoreIndustryTable,
  terminalRankClass,
  WatchlistChartGrid,
} from "./components/StrongTables";
import { useStrongPage } from "./useStrongPage";
import { Target, TrendingUp, Layers } from "lucide-react";
import "../../styles/cockpit.css";

const panelSummaryClass =
  "p-4 bg-slate-900/40 hover:bg-slate-800/40 transition-colors font-black text-sm text-slate-300 uppercase tracking-widest flex items-center justify-between list-none cursor-pointer";

export function StrongPage() {
  const {
    snapshot,
    rsStatus,
    rsStatusError,
    search,
    setSearch,
    topListCount,
    watchlist,
    pulseLine,
    filteredIndustries,
  } = useStrongPage();

  const industryNames = new Map(
    (snapshot?.industries || []).map((row) => [row.industry_key, row.name]),
  );

  return (
    <AppShell
      title="Strong Industry Terminal"
      source="Source: Finviz Top industries · Yahoo RS watchlist · Daily automation"
    >
      <div className="cockpit-preview max-w-[1600px] mx-auto px-4 md:px-6 py-6 space-y-6">
        <div
          className={`rounded-lg border px-4 py-3 font-mono text-xs tracking-wide ${
            rsStatusError
              ? "bg-rose-950/20 border-rose-900/50 text-rose-300"
              : "bg-[#0b0f19] border-slate-800 text-slate-400"
          }`}
        >
          <p className="text-slate-200">{pulseLine}</p>
          {rsStatus && rsStatusError ? (
            <p className="text-rose-400 mt-1 text-[10px]">{rsStatus}</p>
          ) : null}
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
              RS top 10% · price &gt; SMA20/50/200 · 30d avg $100M+ · top 100 · Yahoo industry
            </p>
          </div>
          <WatchlistChartGrid watchlist={watchlist} industryNames={industryNames} />
        </section>

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
