import {
  computeLongTrend,
  computeShortTrend,
  finvizDailyChartUrl,
  getTopStrongIndustries,
  normalizeTrendLabel,
  pct,
  perfScales,
  rankHeat,
  rankItemClass,
  trendBadgeClass,
  type IndustryRow,
  type RsPayload,
  type SnapshotPayload,
} from "../../../lib/industry";

export function TrendBadge({ text }: { text: string }) {
  if (!text) return <>—</>;
  const label = normalizeTrendLabel(text);
  return <span className={trendBadgeClass(label)}>{label}</span>;
}

export function PerfMicroBar({ value, maxAbs }: { value: number; maxAbs: number }) {
  const v = Number(value);
  if (!Number.isFinite(v)) {
    return (
      <span className="perf-cell">
        <span className="perf-val">—</span>
      </span>
    );
  }
  const sign = v >= 0 ? "pos" : "neg";
  const scale = Math.max(Number(maxAbs) || 0.01, 0.01);
  const width = Math.min(100, Math.max(6, (Math.abs(v) / scale) * 100));
  return (
    <span className="perf-cell">
      <span className="perf-bar-wrap" aria-hidden="true">
        <span className={`perf-bar ${sign}`} style={{ width: `${width.toFixed(1)}%` }} />
      </span>
      <span className={`perf-val ${sign}`}>{pct(v)}</span>
    </span>
  );
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
      className="rank-compact"
      aria-label={`Rank W${row.rank_w} M${row.rank_m} Q${row.rank_q} H${row.rank_h} Y${row.rank_y}`}
    >
      {items.map(([label, rank]) => (
        <span
          key={label}
          className={`rank-item ${rankItemClass(rank)}`}
          title={`${label} rank ${rank} — lower is stronger`}
        >
          <span className="rank-item-l">{label}</span>
          <span className="rank-item-n">{rank}</span>
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
          <td colSpan={11} className="hint">
            No snapshot yet — daily run in progress…
          </td>
        </tr>
      </tbody>
    );
  }

  return (
    <tbody>
      {top.map((row) => (
        <tr key={row.industry_key} data-key={row.industry_key}>
          <td>
            <a className="industry-link" href={row.finviz_url} target="_blank" rel="noreferrer">
              {row.name}
            </a>
          </td>
          <td className="num">{row.stocks}</td>
          <td className="num score-cell">{row.score.toFixed(3)}</td>
          <td>
            <PerfMicroBar value={row.perf_w} maxAbs={scales.perf_w} />
          </td>
          <td>
            <PerfMicroBar value={row.perf_m} maxAbs={scales.perf_m} />
          </td>
          <td>
            <PerfMicroBar value={row.perf_q} maxAbs={scales.perf_q} />
          </td>
          <td>
            <PerfMicroBar value={row.perf_h} maxAbs={scales.perf_h} />
          </td>
          <td>
            <PerfMicroBar value={row.perf_y} maxAbs={scales.perf_y} />
          </td>
          <td className="ranks-cell">
            <RankCompactRow row={row} />
          </td>
          <td>
            <TrendBadge text={computeShortTrend(row)} />
          </td>
          <td>
            <TrendBadge text={computeLongTrend(row)} />
          </td>
        </tr>
      ))}
    </tbody>
  );
}

export function WatchlistChartGrid({ watchlist }: { watchlist: RsPayload["watchlist"] }) {
  if (!watchlist.length) {
    return <p className="hint">Charts appear after the daily watchlist is built.</p>;
  }
  return (
    <div className="watchlist-chart-grid">
      {watchlist.map((row) => (
        <article key={row.symbol} className="watchlist-chart-card">
          <a
            href={`https://finviz.com/quote.ashx?t=${encodeURIComponent(row.symbol)}`}
            target="_blank"
            rel="noreferrer"
          >
            <img
              className="watchlist-chart-img"
              src={finvizDailyChartUrl(row.symbol)}
              alt={`${row.symbol} daily chart`}
              loading="lazy"
            />
          </a>
        </article>
      ))}
    </div>
  );
}

export function fmtPerf(v: unknown) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  return `${Number(v).toFixed(1)}%`;
}

export function rankHeatClass(rank: number) {
  return rankHeat(rank);
}
