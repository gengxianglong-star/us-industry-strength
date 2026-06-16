import { useMemo } from "react";
import type { WatchlistChartBar } from "../../../lib/industry";
import { finvizDailyChartUrl } from "../../../lib/industry";

function CandlestickSvg({ bars }: { bars: WatchlistChartBar[] }) {
  const svg = useMemo(() => {
    const slice = bars.filter(
      (b) =>
        Number.isFinite(b.o) &&
        Number.isFinite(b.h) &&
        Number.isFinite(b.l) &&
        Number.isFinite(b.c),
    );
    if (slice.length < 2) return null;

    const W = 400;
    const H = 200;
    const PAD = 4;
    const lows = slice.map((b) => b.l);
    const highs = slice.map((b) => b.h);
    const min = Math.min(...lows);
    const max = Math.max(...highs);
    const range = max - min || 1;
    const innerW = W - PAD * 2;
    const innerH = H - PAD * 2;
    const slot = innerW / slice.length;
    const y = (price: number) => PAD + ((max - price) / range) * innerH;

    const candles = slice
      .map((bar, i) => {
        const cx = PAD + i * slot + slot / 2;
        const bodyTop = y(Math.max(bar.o, bar.c));
        const bodyBot = y(Math.min(bar.o, bar.c));
        const bodyH = Math.max(bodyBot - bodyTop, 0.8);
        const up = bar.c >= bar.o;
        const color = up ? "#34d399" : "#f87171";
        const bodyW = Math.max(slot * 0.55, 1);
        return `<line x1="${cx}" y1="${y(bar.h)}" x2="${cx}" y2="${y(bar.l)}" stroke="${color}" stroke-width="1"></line><rect x="${cx - bodyW / 2}" y="${bodyTop}" width="${bodyW}" height="${bodyH}" fill="${color}"></rect>`;
      })
      .join("");

    return { W, H, candles };
  }, [bars]);

  if (!svg) {
    return (
      <div className="w-full h-full flex items-center justify-center text-[10px] font-mono text-slate-600">
        Chart unavailable
      </div>
    );
  }

  return (
    <svg
      className="w-full h-full"
      viewBox={`0 0 ${svg.W} ${svg.H}`}
      preserveAspectRatio="none"
      role="img"
      aria-hidden="true"
    >
      <rect x="0" y="0" width={svg.W} height={svg.H} fill="#000" />
      <g dangerouslySetInnerHTML={{ __html: svg.candles }} />
    </svg>
  );
}

export function WatchlistFinvizChart({
  symbol,
  bars,
}: {
  symbol: string;
  bars?: WatchlistChartBar[];
}) {
  const hasBars = (bars?.length ?? 0) >= 2;

  if (hasBars) {
    return (
      <div className="w-full h-full bg-black overflow-hidden">
        <CandlestickSvg bars={bars!} />
      </div>
    );
  }

  const imageUrl = finvizDailyChartUrl(symbol);
  return (
    <div className="w-full h-full bg-black flex items-center justify-center overflow-hidden">
      <img
        src={imageUrl}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        className="w-full h-full object-contain"
        onError={(e) => {
          const img = e.currentTarget;
          img.style.display = "none";
          const parent = img.parentElement;
          if (parent && !parent.querySelector("[data-chart-fallback]")) {
            const fallback = document.createElement("div");
            fallback.dataset.chartFallback = "1";
            fallback.className =
              "text-[10px] font-mono text-slate-600 text-center px-2";
            fallback.textContent = "Chart unavailable";
            parent.appendChild(fallback);
          }
        }}
      />
    </div>
  );
}

/** @deprecated Use WatchlistFinvizChart */
export function WatchlistLightweightChart({
  symbol,
  bars,
}: {
  symbol?: string;
  bars?: WatchlistChartBar[];
}) {
  if (!symbol) {
    return (
      <div className="h-full flex items-center justify-center bg-black text-[10px] font-mono text-slate-600">
        Chart unavailable
      </div>
    );
  }
  return <WatchlistFinvizChart symbol={symbol} bars={bars} />;
}

export function tradingViewUrl(symbol: string, exchange?: string | null) {
  const ex = (exchange || "NASDAQ").toUpperCase().replace(/\s+/g, "");
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(`${ex}:${symbol}`)}`;
}
