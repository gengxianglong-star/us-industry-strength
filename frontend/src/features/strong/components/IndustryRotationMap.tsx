import { useMemo } from "react";
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
} from "recharts";
import { Crosshair } from "lucide-react";
import type { IndustryRow } from "../../../lib/industry";
import { buildAlphaRotationNodes, type RotationNode } from "../../../lib/rotationLogic";

type ScatterDotProps = {
  cx?: number;
  cy?: number;
  payload?: RotationNode;
};

function VectorScatterDot({ cx = 0, cy = 0, payload }: ScatterDotProps) {
  if (!payload) return null;
  const { rs_3m, rs_1m, delta_1w } = payload;

  let dotColor = "#10b981";
  if (rs_3m < 50 && rs_1m >= 50) dotColor = "#06b6d4";
  else if (rs_3m >= 50 && rs_1m < 50) dotColor = "#f59e0b";
  else if (rs_3m < 50 && rs_1m < 50) dotColor = "#ef4444";

  const isPositive = delta_1w >= 0;
  const absDelta = Math.abs(delta_1w);
  const arrowLength = Math.min(Math.max(absDelta * 0.8, 5), 30);
  const arrowColor = isPositive ? "#06b6d4" : "#f59e0b";

  return (
    <g style={{ cursor: "pointer" }}>
      {absDelta > 2 &&
        (isPositive ? (
          <path
            d={`M ${cx - 3.5} ${cy - 8} L ${cx + 3.5} ${cy - 8} L ${cx} ${cy - 8 - arrowLength} Z`}
            fill={arrowColor}
            opacity={0.85}
          />
        ) : (
          <path
            d={`M ${cx - 3.5} ${cy + 8} L ${cx + 3.5} ${cy + 8} L ${cx} ${cy + 8 + arrowLength} Z`}
            fill={arrowColor}
            opacity={0.85}
          />
        ))}
      <circle
        cx={cx}
        cy={cy}
        r={6.5}
        fill={dotColor}
        stroke="#0f172a"
        strokeWidth={1.5}
        className="drop-shadow-[0_0_5px_rgba(255,255,255,0.3)]"
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
        <span className="text-slate-400 uppercase tracking-widest text-[9px]">1W Vector:</span>
        <span className={`font-black ${d.delta_1w >= 0 ? "text-cyan-400" : "text-amber-500"}`}>
          {d.delta_1w >= 0 ? "▲ +" : "▼ "}
          {d.delta_1w.toFixed(0)}
        </span>
      </div>
    </div>
  );
}

function adaptiveRsDomain(values: number[]): [number, number] {
  if (values.length === 0) return [40, 100];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = Math.max(10, (max - min) * 0.12);
  let lo = Math.floor(min - pad);
  let hi = Math.ceil(max + pad);
  if (hi - lo < 35) {
    const mid = (min + max) / 2;
    lo = Math.floor(mid - 18);
    hi = Math.ceil(mid + 18);
  }
  return [Math.max(0, lo), Math.min(100, hi)];
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
  const alphaNodes = useMemo(
    () => buildAlphaRotationNodes(industries, breadthRatio10),
    [industries, breadthRatio10],
  );

  const xDomain = useMemo(
    () => adaptiveRsDomain(alphaNodes.map((n) => n.rs_3m)),
    [alphaNodes],
  );
  const yDomain = useMemo(
    () => adaptiveRsDomain(alphaNodes.map((n) => n.rs_1m)),
    [alphaNodes],
  );
  const midX = xDomain[0] <= 50 && 50 <= xDomain[1] ? 50 : null;
  const midY = yDomain[0] <= 50 && 50 <= yDomain[1] ? 50 : null;

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
          X: 3M RS · Y: 1M RS · Arrow: 1W momentum · Top10 ∪ ({alphaNodes.length} industries)
        </p>
        <div className="flex flex-wrap gap-4 text-[9px] font-mono uppercase font-bold mt-3 pt-2 border-t border-slate-800/60">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" /> Leaders
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#06b6d4]" /> Ignition
          </span>
          <span className="flex items-center gap-1.5 text-cyan-400">▲ Accel</span>
          <span className="flex items-center gap-1.5 text-amber-500">▼ Decel</span>
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
                dataKey="rs_3m"
                domain={xDomain}
                stroke="#475569"
                tick={{ fontSize: 10, fill: "#475569" }}
                allowDataOverflow
              />
              <YAxis
                type="number"
                dataKey="rs_1m"
                domain={yDomain}
                stroke="#475569"
                tick={{ fontSize: 10, fill: "#475569" }}
                allowDataOverflow
              />
              {midX != null && midY != null ? (
                <ReferenceArea x1={midX} x2={xDomain[1]} y1={midY} y2={yDomain[1]} fill="#10b981" fillOpacity={0.03} />
              ) : null}
              {midX != null && midY != null ? (
                <ReferenceArea x1={xDomain[0]} x2={midX} y1={midY} y2={yDomain[1]} fill="#06b6d4" fillOpacity={0.03} />
              ) : null}
              {midX != null && midY != null ? (
                <ReferenceArea x1={midX} x2={xDomain[1]} y1={yDomain[0]} y2={midY} fill="#f59e0b" fillOpacity={0.03} />
              ) : null}
              {midX != null ? <ReferenceLine x={midX} stroke="#334155" strokeWidth={2} /> : null}
              {midY != null ? <ReferenceLine y={midY} stroke="#334155" strokeWidth={2} /> : null}
              <Tooltip
                content={<RotationTooltip />}
                cursor={{ strokeDasharray: "3 3", stroke: "#475569", strokeWidth: 1 }}
                isAnimationActive={false}
              />
              <Scatter
                data={alphaNodes}
                isAnimationActive={false}
                shape={(props: ScatterDotProps) => <VectorScatterDot {...props} />}
              />
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
