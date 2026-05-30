import { AppShell } from "../../components/layout/AppShell";
import { IS_READONLY } from "../../lib/api";
import { getTopStrongIndustries } from "../../lib/industry";
import { ConfigPanel } from "./components/ConfigPanel";
import {
  CoreIndustryTable,
  fmtPerf,
  rankHeatClass,
  WatchlistChartGrid,
} from "./components/StrongTables";
import { useStrongPage } from "./useStrongPage";

export function StrongPage() {
  const {
    snapshot,
    rsPayload,
    rsStatus,
    rsStatusError,
    search,
    setSearch,
    topListCount,
    summaryText,
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

  return (
    <AppShell
      title="Strong Industry"
      source="Source: Finviz Industry Groups · Yahoo Finance (RS) · Finviz Screener"
    >
      <section className="summary" aria-label="Snapshot overview">
        <p className="snapshot-meta">{summaryText}</p>
      </section>

      <section className="panel panel-hero" aria-label="Decision center">
        <div className="panel-header-row panel-header-row-status-only">
          <span
            className={rsStatusError ? "inline-status error" : "inline-status"}
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            {rsStatus}
          </span>
        </div>
        <div className="decision-grid">
          <div className="table-wrap decision-core-wrap">
            <table aria-label="Strong industries top list">
              <thead>
                <tr>
                  <th scope="col">Industry</th>
                  <th scope="col">Stocks</th>
                  <th scope="col">Score</th>
                  <th scope="col">1W</th>
                  <th scope="col">1M</th>
                  <th scope="col">3M</th>
                  <th scope="col">6M</th>
                  <th scope="col">1Y</th>
                  <th scope="col" title="W/M/Q/H/Y rank — lower is stronger">
                    Rank
                  </th>
                  <th scope="col" title="Short-term trend vs 3M rank">
                    Short
                  </th>
                  <th scope="col" title="Long-term trend vs 6M rank">
                    Long
                  </th>
                </tr>
              </thead>
              <CoreIndustryTable snapshot={snapshot} />
            </table>
          </div>
          <div className="decision-watchlist-wrap" aria-label="Final watchlist daily charts">
            <WatchlistChartGrid watchlist={watchlist} />
          </div>
        </div>
      </section>

      <details className="panel panel-secondary" id="rsPanel">
        <summary>Evidence A: Stock RS</summary>
        <p className="hint">Confirm watchlist names still rank near the top on market-wide RS.</p>
        <div className="coverage-panel">
          {meta ? (
            <>
              <span className="coverage-item">Universe {meta.universe_count}</span>
              <span className="coverage-item">Covered {covered}</span>
              <span className="coverage-item">Main RS {meta.computed_count}</span>
              <span className="coverage-item">New IPO RS {newStockRsCount}</span>
              <span className="coverage-item">New list {meta.new_stock_leaderboard_count ?? 0}</span>
              <span className="coverage-item">No bars {meta.no_bars_count}</span>
            </>
          ) : (
            <span className="hint">Coverage: waiting on RS run</span>
          )}
        </div>
        <div className="hint">Prices: Yahoo adj. close</div>
        <div className="table-wrap table-scroll medium-scroll">
          <h3 className="subheading">RS Top</h3>
          <table aria-label="Stock RS top list">
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col">Score</th>
                <th scope="col">Tier</th>
                <th scope="col">1W</th>
                <th scope="col">1M</th>
                <th scope="col">3M</th>
                <th scope="col">6M</th>
                <th scope="col">1Y</th>
                <th scope="col">Rank W/M/Q/H/Y</th>
              </tr>
            </thead>
            <tbody>
              {(rsPayload?.rows || []).length === 0 ? (
                <tr>
                  <td colSpan={9} className="hint">
                    No RS data yet — fills in after the daily run.
                  </td>
                </tr>
              ) : (
                rsPayload!.rows.map((row) => (
                  <tr key={String(row.symbol)}>
                    <td>
                      <a
                        className="industry-link"
                        href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(String(row.symbol))}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {String(row.symbol)}
                      </a>
                    </td>
                    <td>{Number(row.rs_score).toFixed(3)}</td>
                    <td>{String(row.tier)}</td>
                    <td className={Number(row.perf_w) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_w)}</td>
                    <td className={Number(row.perf_m) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_m)}</td>
                    <td className={Number(row.perf_q) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_q)}</td>
                    <td className={Number(row.perf_h) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_h)}</td>
                    <td className={Number(row.perf_y) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_y)}</td>
                    <td>
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
        <div className="table-wrap table-scroll medium-scroll">
          <h3 className="subheading">New Stock RS Leaderboard (Top 10% per cohort)</h3>
          <p className="hint">
            M/Q/H/3Q cohorts (22–259 bars). Only top 10% per cohort can cross with Top15 Finviz picks for the
            final watchlist.
          </p>
          <table aria-label="New stock RS leaderboard">
            <thead>
              <tr>
                <th scope="col">Cohort</th>
                <th scope="col">Symbol</th>
                <th scope="col">Bars</th>
                <th scope="col">Score</th>
                <th scope="col">Tier</th>
                <th scope="col">1W</th>
                <th scope="col">1M</th>
                <th scope="col">3M</th>
                <th scope="col">6M</th>
                <th scope="col">3Q≈189D</th>
              </tr>
            </thead>
            <tbody>
              {(rsPayload?.new_stock_leaderboard || []).length === 0 ? (
                <tr>
                  <td colSpan={9} className="hint">
                    No new-issue RS leaderboard yet
                  </td>
                </tr>
              ) : (
                rsPayload!.new_stock_leaderboard.map((row, idx) => (
                  <tr key={`${row.symbol}-${idx}`}>
                    <td>{NEW_STOCK_COHORT_LABEL[String(row.cohort)] || String(row.cohort)}</td>
                    <td>
                      <a
                        className="industry-link"
                        href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(String(row.symbol))}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {String(row.symbol)}
                      </a>
                    </td>
                    <td>{row.bar_count != null ? String(row.bar_count) : "—"}</td>
                    <td>{Number(row.rs_score).toFixed(3)}</td>
                    <td>{String(row.tier)}</td>
                    <td className={Number(row.perf_w) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_w)}</td>
                    <td className={Number(row.perf_m) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_m)}</td>
                    <td className={Number(row.perf_q) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_q)}</td>
                    <td className={Number(row.perf_h) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_h)}</td>
                    <td className={Number(row.perf_tq) >= 0 ? "pos" : "neg"}>{fmtPerf(row.perf_tq)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </details>

      <details className="panel" id="strongCardsPanel">
        <summary>Evidence B: Industry Stock Picks</summary>
        <p className="hint">Finviz screen hits inside the strongest groups.</p>
        <div className="strong-cards compact-scroll">
          {(snapshot ? getTopStrongIndustries(snapshot) : []).map((row, idx) => (
            <article key={row.industry_key} className="strong-card" data-key={row.industry_key}>
              <header className="strong-card-header">
                <div className="strong-card-title-wrap">
                  <span className="strong-card-rank">#{idx + 1}</span>
                  <a className="industry-link strong-card-title" href={row.finviz_url} target="_blank" rel="noreferrer">
                    {row.name}
                  </a>
                </div>
                <div className="strong-card-right">
                  <span className="strong-card-hits">{(row.stock_picks || []).length} names</span>
                  <span className="strong-card-meta">Score {row.score.toFixed(3)}</span>
                </div>
              </header>
              {row.stock_picks_error ? (
                <p className="hint error-text">{row.stock_picks_error}</p>
              ) : (row.stock_picks || []).length === 0 ? (
                <p className="hint">
                  No hits{" "}
                  {row.stock_screener_url ? (
                    <a className="industry-link" href={row.stock_screener_url} target="_blank" rel="noreferrer">
                      Open in Finviz
                    </a>
                  ) : null}
                </p>
              ) : (
                <ul className="ticker-list">
                  {(row.stock_picks || []).map((t) => (
                    <li key={t}>
                      <a
                        className="ticker-chip"
                        href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(t)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {t}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      </details>

      <details className="panel all-industries-panel">
        <summary>Reference: All Industries (Rank Heatmap)</summary>
        <p className="hint">Full sector rank map — expand when you need backup groups.</p>
        <label className="sr-only" htmlFor="searchInput">
          Search industries
        </label>
        <input
          id="searchInput"
          type="search"
          name="industry_search"
          placeholder="Search industry…"
          autoComplete="off"
          spellCheck={false}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="table-wrap">
          <table aria-label="All industries rank heatmap">
            <thead>
              <tr>
                <th scope="col">Industry</th>
                <th scope="col">Stocks</th>
                <th scope="col">Score</th>
                <th scope="col">Rank W</th>
                <th scope="col">Rank M</th>
                <th scope="col">Rank Q</th>
                <th scope="col">Rank H</th>
                <th scope="col">Rank Y</th>
                <th scope="col">Status</th>
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
                  <tr key={row.industry_key} data-key={row.industry_key} className={row.excluded ? "excluded" : ""}>
                    <td>{row.name}</td>
                    <td>{row.stocks}</td>
                    <td>{row.excluded ? "—" : row.score.toFixed(3)}</td>
                    <td className={rankHeatClass(row.rank_w)}>{row.rank_w}</td>
                    <td className={rankHeatClass(row.rank_m)}>{row.rank_m}</td>
                    <td className={rankHeatClass(row.rank_q)}>{row.rank_q}</td>
                    <td className={rankHeatClass(row.rank_h)}>{row.rank_h}</td>
                    <td className={rankHeatClass(row.rank_y)}>{row.rank_y}</td>
                    <td>{status}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>

      {!IS_READONLY ? <ConfigPanel /> : null}

      <footer>
        <p>
          Data:{" "}
          <a href="https://finviz.com/groups?g=industry&v=210&o=name" target="_blank" rel="noreferrer">
            Finviz Industry Groups
          </a>{" "}
          (15 min delay) · Research only, not investment advice
        </p>
      </footer>
    </AppShell>
  );
}
