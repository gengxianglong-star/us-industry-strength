import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { WatchlistChartBar } from "../../../lib/industry";

const CHART_DISPLAY_BARS = 44;

const MA_COLORS = {
  10: "#facc15",
  20: "#fb923c",
  50: "#22d3ee",
} as const;

function toChartTime(d: string): UTCTimestamp {
  return Math.floor(new Date(`${d}T00:00:00Z`).getTime() / 1000) as UTCTimestamp;
}

function sma(values: number[], period: number): (number | null)[] {
  return values.map((_, i) => {
    if (i + 1 < period) return null;
    const slice = values.slice(i + 1 - period, i + 1);
    return slice.reduce((a, b) => a + b, 0) / period;
  });
}

function buildMaLineData(
  bars: WatchlistChartBar[],
  period: number,
  fromDate?: string,
) {
  const closes = bars.map((b) => b.c);
  const ma = sma(closes, period);
  const out: { time: UTCTimestamp; value: number }[] = [];
  bars.forEach((bar, i) => {
    const v = ma[i];
    if (v != null && Number.isFinite(v) && (!fromDate || bar.d >= fromDate)) {
      out.push({ time: toChartTime(bar.d), value: v });
    }
  });
  return out;
}

export function WatchlistLightweightChart({ bars }: { bars?: WatchlistChartBar[] }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartApi = useRef<IChartApi | null>(null);
  const [active, setActive] = useState(false);

  const { series, display } = useMemo(() => {
    const valid = (bars || []).filter(
      (b) =>
        Number.isFinite(b.o) &&
        Number.isFinite(b.h) &&
        Number.isFinite(b.l) &&
        Number.isFinite(b.c),
    );
    const visible = valid.slice(-CHART_DISPLAY_BARS);
    return { series: valid, display: visible };
  }, [bars]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el || display.length < 10) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) setActive(true);
      },
      { rootMargin: "120px", threshold: 0.05 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [display.length]);

  useEffect(() => {
    if (!active || !chartRef.current || display.length < 10) return undefined;
    const windowStart = display[0]?.d;

    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 200,
      layout: {
        background: { type: ColorType.Solid, color: "#000000" },
        textColor: "#64748b",
        fontSize: 10,
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      localization: {
        locale: "en-US",
      },
      crosshair: { vertLine: { visible: false }, horzLine: { visible: false } },
      handleScroll: false,
      handleScale: false,
    });
    chartApi.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#34d399",
      downColor: "#f87171",
      borderUpColor: "#34d399",
      borderDownColor: "#f87171",
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
    });
    candleSeries.setData(
      display.map((b) => ({
        time: toChartTime(b.d),
        open: b.o,
        high: b.h,
        low: b.l,
        close: b.c,
      })),
    );
    candleSeries.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.28 } });

    ([10, 20, 50] as const).forEach((period) => {
      const line = chart.addSeries(LineSeries, {
        color: MA_COLORS[period],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(buildMaLineData(series, period, windowStart));
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    volumeSeries.setData(
      display.map((b) => ({
        time: toChartTime(b.d),
        value: b.v ?? 0,
        color: b.c >= b.o ? "rgba(52, 211, 153, 0.45)" : "rgba(248, 113, 113, 0.45)",
      })),
    );
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chart.timeScale().fitContent();

    const onResize = () => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth });
      }
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(chartRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartApi.current = null;
    };
  }, [active, display, series, bars]);

  if (display.length < 10) {
    return (
      <div className="h-[200px] flex items-center justify-center bg-black text-[10px] font-mono text-slate-600">
        Chart unavailable
      </div>
    );
  }

  return (
    <div ref={wrapRef} className="bg-black min-h-[200px]">
      {!active ? (
        <div className="h-[200px] flex items-center justify-center text-[10px] font-mono text-slate-700">
          …
        </div>
      ) : (
        <div ref={chartRef} className="w-full" />
      )}
    </div>
  );
}

export function pctVsMa(bars: WatchlistChartBar[] | undefined, period: number): number | null {
  const all = bars || [];
  if (all.length < period) return null;
  const closes = all.map((b) => b.c);
  const last = closes[closes.length - 1];
  const tail = closes.slice(-period);
  const ma = tail.reduce((a, b) => a + b, 0) / period;
  if (!ma) return null;
  return ((last - ma) / ma) * 100;
}

export function tradingViewUrl(symbol: string, exchange?: string | null) {
  const ex = (exchange || "NASDAQ").toUpperCase().replace(/\s+/g, "");
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(`${ex}:${symbol}`)}`;
}
