import { useMemo, useState } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  Customized,
} from "recharts";
import { Crosshair } from "lucide-react";
import type { IndustryRow } from "../../../lib/industry";
import { buildAlphaRotationNodes, type RotationNode } from "../../../lib/rotationLogic";

type ScatterDotProps = {
  cx?: number;
  cy?: number;
  payload?: RotationNode;
  hoveredKey?: string | null;
};

function VectorScatterDot({ cx = 0, cy = 0, payload, hoveredKey }: ScatterDotProps) {
  if (!payload) return null;
  const { rs_3m, rs_1m, industry_key } = payload;
  const isHovered = hoveredKey === industry_key;

  let dotColor = "#10b981";
  if (rs_3m < 50 && rs_1m >= 50) dotColor = "#06b6d4";
  else if (rs_3m >= 50 && rs_1m < 50) dotColor = "#f59e0b";
  else if (rs_3m < 50 && rs_1m < 50) dotColor = "#ef4444";

  const radius = isHovered ? 9 : 6.5;

  return (
    <g style={{ cursor: "pointer" }}>
      {isHovered ? (
        <circle
          cx={cx}
          cy={cy}
          r={radius + 4}
          fill="none"
          stroke="#22d3ee"
          strokeWidth={1.5}
          opacity={0.55}
        />
      ) : null}
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill={dotColor}
        stroke={isHovered ? "#22d3ee" : "#0f172a"}
        strokeWidth={isHovered ? 2 : 1.5}
        className={isHovered ? "drop-shadow-[0_0_10px_rgba(34,211,238,0.55)]" : "drop-shadow-[0_0_5px_rgba(255,255,255,0.3)]"}
      />
    </g>
  );
}

function RotationTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: RotationNode }>;
}) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-slate-900 border border-slate-700 p-3 rounded-lg shadow-2xl text-xs font-mono z-[100]">
      <div className="font-black text-slate-100 mb-2 text-sm uppercase tracking-widest border-b border-slate-800 pb-1 flex justify-between gap-4">
        <span>{d.name}</span>
        <span className="text-[9px] text-slate-500 shrink-0">6M: {d.rs_score.toFixed(0)}</span>
      </div>
      <div className="text-emerald-500">
        3M RS: <span className="font-bold text-slate-200">{d.rs_3m.toFixed(0)}</span>
      </div>
      <div className="text-emerald-400 mt-0.5">
        1M RS: <span className="font-bold text-slate-200">{d.rs_1m.toFixed(0)}</span>
      </div>
      <div className="mt-2 pt-2 border-t border-slate-800 flex items-center gap-1.5">
        <span className="text-slate-400 uppercase tracking-widest text-[9px]">1W Δ:</span>
        <span className={`font-black ${d.delta_1w >= 0 ? "text-cyan-400" : "text-amber-500"}`}>
          {d.delta_1w >= 0 ? "▲ +" : "▼ "}
          {d.delta_1w.toFixed(0)}
        </span>
      </div>
      {d.trajectory_5d.length >= 2 ? (
        <div className="mt-1 text-[9px] text-slate-500">{d.trajectory_5d.length}d trail on hover</div>
      ) : null}
    </div>
  );
}

const PLOT_MARGIN = 8;

type AlphaPlotNode = RotationNode & { plot_x: number; plot_y: number };

type PlotTransform = {
  plotNodes: AlphaPlotNode[];
  mapRsPoint: (rs_3m: number, rs_1m: number) => { plot_x: number; plot_y: number };
  xTicks: Array<{ plot: number; label: string }>;
  yTicks: Array<{ plot: number; label: string }>;
  midX: number | null;
  midY: number | null;
};

function stableJitter(key: string, amp: number): { jx: number; jy: number } {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
  return {
    jx: ((h & 255) / 255 - 0.5) * amp,
    jy: (((h >> 8) & 255) / 255 - 0.5) * amp,
  };
}

/** Spread alpha industries across the plot (they cluster at high absolute RS). */
function buildAlphaPlot(nodes: RotationNode[]): PlotTransform {
  if (nodes.length === 0) {
    return {
      plotNodes: [],
      mapRsPoint: (rs_3m, rs_1m) => ({ plot_x: rs_3m, plot_y: rs_1m }),
      xTicks: [],
      yTicks: [],
      midX: null,
      midY: null,
    };
  }

  const xVals = nodes.map((n) => n.rs_3m);
  const yVals = nodes.map((n) => n.rs_1m);
  const dataXMin = Math.min(...xVals);
  const dataYMin = Math.min(...yVals);

  // Widen the axis floor so high-RS leaders in the top-right occupy more plot area.
  const AXIS_FLOOR = 42;
  const AXIS_CEIL = 100;
  const xMin = Math.min(dataXMin - 6, AXIS_FLOOR);
  const xMax = AXIS_CEIL;
  const yMin = Math.min(dataYMin - 6, AXIS_FLOOR);
  const yMax = AXIS_CEIL;
  const xSpan = Math.max(xMax - xMin, 28);
  const ySpan = Math.max(yMax - yMin, 28);

  const toPlotX = (v: number) =>
    PLOT_MARGIN + ((v - xMin) / xSpan) * (100 - 2 * PLOT_MARGIN);
  const toPlotY = (v: number) =>
    PLOT_MARGIN + ((v - yMin) / ySpan) * (100 - 2 * PLOT_MARGIN);

  const mapRsPoint = (rs_3m: number, rs_1m: number) => ({
    plot_x: Math.min(100 - PLOT_MARGIN, Math.max(PLOT_MARGIN, toPlotX(rs_3m))),
    plot_y: Math.min(100 - PLOT_MARGIN, Math.max(PLOT_MARGIN, toPlotY(rs_1m))),
  });

  const plotNodes: AlphaPlotNode[] = nodes.map((n) => {
    const { jx, jy } = stableJitter(n.industry_key, 3.8);
    const base = mapRsPoint(n.rs_3m, n.rs_1m);
    return {
      ...n,
      plot_x: Math.min(100 - PLOT_MARGIN, Math.max(PLOT_MARGIN, base.plot_x + jx)),
      plot_y: Math.min(100 - PLOT_MARGIN, Math.max(PLOT_MARGIN, base.plot_y + jy)),
    };
  });

  const tickVals = (min: number, max: number) => {
    const step = max - min >= 40 ? 10 : 5;
    const start = Math.ceil(min / step) * step;
    const vals: number[] = [];
    for (let v = start; v <= max; v += step) vals.push(v);
    if (vals.length === 0 || vals[0] > min) vals.unshift(Math.round(min));
    if (vals[vals.length - 1] < max) vals.push(Math.round(max));
    return vals;
  };

  return {
    plotNodes,
    mapRsPoint,
    xTicks: tickVals(xMin, xMax).map((v) => ({ plot: toPlotX(v), label: String(v) })),
    yTicks: tickVals(yMin, yMax).map((v) => ({ plot: toPlotY(v), label: String(v) })),
    midX: 50 >= xMin && 50 <= xMax ? toPlotX(50) : null,
    midY: 50 >= yMin && 50 <= yMax ? toPlotY(50) : null,
  };
}

type AxisMap = Record<string, { scale?: (v: number) => number }>;

function TrajectoryTail({
  hoveredKey,
  plotNodes,
  mapRsPoint,
  xAxisMap,
  yAxisMap,
  offset,
}: {
  hoveredKey: string | null;
  plotNodes: AlphaPlotNode[];
  mapRsPoint: PlotTransform["mapRsPoint"];
  xAxisMap?: AxisMap;
  yAxisMap?: AxisMap;
  offset?: { left?: number; top?: number };
}) {
  if (!hoveredKey || !xAxisMap || !yAxisMap || !offset) return null;
  const node = plotNodes.find((n) => n.industry_key === hoveredKey);
  if (!node?.trajectory_5d || node.trajectory_5d.length < 2) return null;

  const xAxis = Object.values(xAxisMap)[0];
  const yAxis = Object.values(yAxisMap)[0];
  if (!xAxis?.scale || !yAxis?.scale) return null;

  const left = offset.left ?? 0;
  const top = offset.top ?? 0;
  const xScale = xAxis.scale!;
  const yScale = yAxis.scale!;
  const pixelPoints = node.trajectory_5d.map((p) => {
    const plot = mapRsPoint(p.rs_3m, p.rs_1m);
    return {
      date: p.date,
      px: xScale(plot.plot_x) + left,
      py: yScale(plot.plot_y) + top,
    };
  });

  return (
    <g pointerEvents="none">
      <polyline
        points={pixelPoints.map((p) => `${p.px},${p.py}`).join(" ")}
        fill="none"
        stroke="#94a3b8"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.5}
        strokeDasharray="5 4"
      />
      {pixelPoints.slice(0, -1).map((p) => (
        <circle key={p.date} cx={p.px} cy={p.py} r={2.5} fill="#64748b" opacity={0.45} />
      ))}
    </g>
  );
}

export function IndustryRotationMap({
  industries,
  breadthRatio10 = 1,
  className = "",
}: {
  industries: IndustryRow[];
  breadthRatio10?: number;
  className?: string;
}) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const alphaNodes = useMemo(
    () => buildAlphaRotationNodes(industries, breadthRatio10),
    [industries, breadthRatio10],
  );

  const { plotNodes, mapRsPoint, xTicks, yTicks, midX, midY } = useMemo(
    () => buildAlphaPlot(alphaNodes),
    [alphaNodes],
  );

  return (
    <div
      className={`bg-[#0b0f19] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col h-[480px] ${className}`}
    >
      <div className="border-b border-slate-800 pb-3 mb-3">
        <h3 className="text-sm font-black text-slate-200 uppercase tracking-widest font-mono flex items-center gap-2">
          <Crosshair size={16} className="text-cyan-500" />
          Sector Vector Matrix (Alpha Group)
        </h3>
        <p className="text-[10px] text-slate-500 uppercase mt-1">
          X: 3M RS · Y: 1M RS · Alpha-relative spread · Hover: 5d trail · ({alphaNodes.length} industries)
        </p>
        <div className="flex flex-wrap gap-4 text-[9px] font-mono uppercase font-bold mt-3 pt-2 border-t border-slate-800/60">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" /> Leaders
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#06b6d4]" /> Ignition
          </span>
          <span className="flex items-center gap-1.5 text-slate-500">Hover dot → 5-session grey trail</span>
        </div>
      </div>

      <div className="flex-1 w-full min-h-0">
        {alphaNodes.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-500 text-xs font-mono">
            No alpha industries in current snapshot
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 28, right: 20, bottom: 10, left: -12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                type="number"
                dataKey="plot_x"
                domain={[0, 100]}
                ticks={xTicks.map((t) => t.plot)}
                tickFormatter={(plot) => xTicks.find((t) => Math.abs(t.plot - plot) < 0.5)?.label ?? ""}
                stroke="#475569"
                tick={{ fontSize: 10, fill: "#475569" }}
                allowDataOverflow
              />
              <YAxis
                type="number"
                dataKey="plot_y"
                domain={[0, 100]}
                ticks={yTicks.map((t) => t.plot)}
                tickFormatter={(plot) => yTicks.find((t) => Math.abs(t.plot - plot) < 0.5)?.label ?? ""}
                stroke="#475569"
                tick={{ fontSize: 10, fill: "#475569" }}
                allowDataOverflow
              />
              {midX != null && midY != null ? (
                <ReferenceArea x1={midX} x2={100 - PLOT_MARGIN} y1={midY} y2={100 - PLOT_MARGIN} fill="#10b981" fillOpacity={0.03} />
              ) : null}
              {midX != null && midY != null ? (
                <ReferenceArea x1={PLOT_MARGIN} x2={midX} y1={midY} y2={100 - PLOT_MARGIN} fill="#06b6d4" fillOpacity={0.03} />
              ) : null}
              {midX != null && midY != null ? (
                <ReferenceArea x1={midX} x2={100 - PLOT_MARGIN} y1={PLOT_MARGIN} y2={midY} fill="#f59e0b" fillOpacity={0.03} />
              ) : null}
              {midX != null ? <ReferenceLine x={midX} stroke="#334155" strokeWidth={2} /> : null}
              {midY != null ? <ReferenceLine y={midY} stroke="#334155" strokeWidth={2} /> : null}
              <Tooltip
                content={<RotationTooltip />}
                cursor={{ strokeDasharray: "3 3", stroke: "#475569", strokeWidth: 1 }}
                isAnimationActive={false}
              />
              <Customized
                component={(rawProps: unknown) => {
                  const props = rawProps as {
                    xAxisMap?: AxisMap;
                    yAxisMap?: AxisMap;
                    offset?: { left?: number; top?: number };
                  };
                  return (
                    <TrajectoryTail
                      hoveredKey={hoveredKey}
                      plotNodes={plotNodes}
                      mapRsPoint={mapRsPoint}
                      xAxisMap={props.xAxisMap}
                      yAxisMap={props.yAxisMap}
                      offset={props.offset}
                    />
                  );
                }}
              />
              <Scatter
                data={plotNodes}
                isAnimationActive={false}
                onMouseEnter={(node) => {
                  const key = (node as { payload?: RotationNode })?.payload?.industry_key;
                  if (key) setHoveredKey(key);
                }}
                onMouseLeave={() => setHoveredKey(null)}
                shape={(props: ScatterDotProps) => (
                  <VectorScatterDot {...props} hoveredKey={hoveredKey} />
                )}
              />
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
