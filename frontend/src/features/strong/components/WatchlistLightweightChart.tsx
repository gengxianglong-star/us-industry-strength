import { finvizDailyChartUrl } from "../../../lib/industry";

export function WatchlistFinvizChart({ symbol }: { symbol: string }) {
  const imageUrl = finvizDailyChartUrl(symbol);

  return (
    <div className="bg-black min-h-[200px] flex items-center justify-center overflow-hidden">
      <img
        src={imageUrl}
        alt={`${symbol} daily chart`}
        referrerPolicy="no-referrer"
        loading="lazy"
        className="w-full h-auto max-h-[280px] object-contain"
      />
    </div>
  );
}

/** @deprecated Use WatchlistFinvizChart — kept for import compatibility */
export function WatchlistLightweightChart({ symbol }: { symbol?: string; bars?: unknown }) {
  if (!symbol) {
    return (
      <div className="h-[200px] flex items-center justify-center bg-black text-[10px] font-mono text-slate-600">
        Chart unavailable
      </div>
    );
  }
  return <WatchlistFinvizChart symbol={symbol} />;
}

export function tradingViewUrl(symbol: string, exchange?: string | null) {
  const ex = (exchange || "NASDAQ").toUpperCase().replace(/\s+/g, "");
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(`${ex}:${symbol}`)}`;
}
