import { useMemo, useState } from "react";
import { finvizChartProxyUrl, finvizDailyChartUrl } from "../../../lib/industry";
import { IS_READONLY } from "../../../lib/api";

function finvizAlternateChartUrl(symbol: string) {
  const t = encodeURIComponent(symbol.trim().toUpperCase());
  return `https://finviz.com/chart.ashx?t=${t}&ty=c&ta=1&p=d&s=l&theme=dark`;
}

export function WatchlistFinvizChart({ symbol }: { symbol: string }) {
  const directUrl = finvizDailyChartUrl(symbol);
  const alternateUrl = finvizAlternateChartUrl(symbol);
  const proxyUrl = finvizChartProxyUrl(symbol);
  const sources = useMemo(
    () => (IS_READONLY ? [directUrl, alternateUrl] : [proxyUrl, directUrl, alternateUrl]),
    [alternateUrl, directUrl, proxyUrl],
  );
  const [index, setIndex] = useState(0);
  const src = sources[Math.min(index, sources.length - 1)];
  const failed = index >= sources.length;

  if (failed) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-black text-[10px] font-mono text-slate-600 text-center px-2">
        <span>Chart unavailable</span>
        <a
          href={directUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-600 hover:text-cyan-400 underline"
        >
          Open Finviz
        </a>
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-black flex items-center justify-center overflow-hidden">
      <img
        src={src}
        alt={`${symbol} daily chart`}
        referrerPolicy="no-referrer"
        loading="lazy"
        className="w-full h-full object-contain"
        onError={() => setIndex((prev) => prev + 1)}
      />
    </div>
  );
}

/** @deprecated Use WatchlistFinvizChart */
export function WatchlistLightweightChart({ symbol }: { symbol?: string }) {
  if (!symbol) {
    return (
      <div className="h-full flex items-center justify-center bg-black text-[10px] font-mono text-slate-600">
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
