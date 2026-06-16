import { useState } from "react";
import { finvizChartProxyUrl, finvizDailyChartUrl } from "../../../lib/industry";
import { IS_READONLY } from "../../../lib/api";

export function WatchlistFinvizChart({ symbol }: { symbol: string }) {
  const directUrl = finvizDailyChartUrl(symbol);
  const proxyUrl = finvizChartProxyUrl(symbol);
  const [src, setSrc] = useState(IS_READONLY ? directUrl : proxyUrl);
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-black text-[10px] font-mono text-slate-600 text-center px-2">
        Chart unavailable
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
        onError={() => {
          if (src === proxyUrl) {
            setSrc(directUrl);
            return;
          }
          setFailed(true);
        }}
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
