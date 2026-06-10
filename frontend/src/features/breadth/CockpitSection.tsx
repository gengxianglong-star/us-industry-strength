import { useEffect, useMemo, useState } from "react";
import { Target, Activity, Zap, Sparkles } from "lucide-react";
import { Area, AreaChart, Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import { fetchJson } from "../../lib/api";
import "../../styles/cockpit.css";

interface BreadthRow {
  date?: string;
  raw_date?: string;
  c1_num?: number;
  c2_num?: number;
  c3_num?: number;
  c4_num?: number;
  c5_num?: number;
  c6_num?: number;
  c7_num?: number;
  c8_num?: number;
  c9_num?: number;
  c10_num?: number;
  c11_num?: number;
  c12_num?: number;
  c14_num?: number;
}

interface BreadthPayload {
  rows?: BreadthRow[];
  coverage?: {
    last_date?: string;
    first_date?: string;
    row_count?: number;
  };
}

type HealthReport = {
  status?: string;
  checks?: Record<string, { ok?: boolean }>;
};

type TerminalHealth = "healthy" | "degraded" | "offline";

const UP4_SPARKLINE_THRESHOLD = 500;
const DN4_SPARKLINE_THRESHOLD = 500;
const SPARKLINE_LOOKBACK_DAYS = 60;
const RATIO_SPARKLINE_THRESHOLD = 2.0;

const HEALTH_UI: Record<
  TerminalHealth,
  { label: string; wrap: string; text: string; dot: string; pulse: boolean }
> = {
  healthy: {
    label: "System Healthy",
    wrap: "bg-emerald-950/20 border-emerald-900/40",
    text: "text-emerald-500",
    dot: "bg-emerald-500 drop-shadow-[0_0_5px_rgba(16,185,129,0.8)]",
    pulse: true,
  },
  degraded: {
    label: "Data Stale — Verify",
    wrap: "bg-amber-950/20 border-amber-900/40",
    text: "text-amber-500",
    dot: "bg-amber-500 drop-shadow-[0_0_5px_rgba(245,158,11,0.8)]",
    pulse: true,
  },
  offline: {
    label: "System Offline",
    wrap: "bg-rose-950/20 border-rose-900/40",
    text: "text-rose-500",
    dot: "bg-rose-500",
    pulse: false,
  },
};

function checkPresent(check: { ok?: boolean } | undefined): boolean {
  if (check == null) return true;
  return check.ok !== false;
}

function resolveTerminalHealth(
  payload: BreadthPayload | null,
  health: HealthReport | null,
): TerminalHealth {
  if (!health || health.status === "error") return "offline";
  const checks = health.checks || {};
  if (!checks.db?.ok) return "offline";

  const latestDate = payload?.rows?.[0]?.date || payload?.rows?.[0]?.raw_date;
  const coverageLast = payload?.coverage?.last_date;
  if (!latestDate && !coverageLast) return "degraded";

  if (health.status === "degraded") return "degraded";
  if (!checkPresent(checks.proxy) || !checkPresent(checks.breadth_source)) return "degraded";
  return "healthy";
}

type SparklineProps = {
  data: BreadthRow[];
  dataKey: keyof BreadthRow;
  threshold: number;
  color?: string;
  neutralColor?: string;
};

function sparklineRowDate(row: BreadthRow | undefined): string {
  return row?.raw_date || row?.date || "";
}

function MicroSparkline({
  data,
  dataKey,
  threshold,
  color = "#10b981",
  neutralColor = "#1e293b",
}: SparklineProps) {
  return (
    <ResponsiveContainer width="100%" height={24}>
      <LineChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
        <YAxis domain={["auto", "auto"]} hide />
        <Line
          type="monotone"
          dataKey={dataKey as string}
          stroke={neutralColor}
          strokeWidth={1.5}
          dot={(props: { cx?: number; cy?: number; payload?: BreadthRow }) => {
            if (props.cx == null || props.cy == null) return null;
            const val = Number(props.payload?.[dataKey] ?? 0);
            if (val >= threshold) {
              const dateLabel = sparklineRowDate(props.payload);
              return (
                <g>
                  {dateLabel ? <title>{dateLabel}</title> : null}
                  <circle cx={props.cx} cy={props.cy} r={4} fill={color} />
                </g>
              );
            }
            return null;
          }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

const T2108_OVERSOLD = 20;
const T2108_OVERBOUGHT = 80;

function CustomT2108Thermometer({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  const oversold = clamped <= T2108_OVERSOLD;
  const overbought = clamped >= T2108_OVERBOUGHT;

  const scaleSpan = 180;
  const zeroY = 210;
  const mercuryHeight = (clamped / 100) * scaleSpan;
  const mercuryY = zeroY - mercuryHeight;

  let mercuryColorId = "mercurySilver";
  let bulbColorId = "bulbSilver";
  let glowFilterId: string | undefined;
  let indicatorColor = "text-slate-400";

  if (overbought) {
    mercuryColorId = "mercuryRed";
    bulbColorId = "bulbRed";
    glowFilterId = "url(#neonGlowRed)";
    indicatorColor = "text-rose-400 drop-shadow-[0_0_4px_rgba(244,63,94,0.6)]";
  } else if (oversold) {
    mercuryColorId = "mercuryGreen";
    bulbColorId = "bulbGreen";
    glowFilterId = "url(#neonGlowGreen)";
    indicatorColor = "text-emerald-400 drop-shadow-[0_0_4px_rgba(16,185,129,0.6)]";
  }

  return (
    <div className="flex flex-col h-full items-center bg-[#090d16]/40 border border-slate-900/60 rounded-xl p-4 shadow-inner relative overflow-hidden">
      <div className="text-[10px] font-mono font-black uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
        <Sparkles
          size={11}
          className={overbought || oversold ? "text-amber-400 animate-pulse" : "text-slate-600"}
        />
        T2108 Scale
      </div>

      <div className="flex-1 w-full flex justify-center items-center min-h-[260px]">
        <svg viewBox="0 0 90 280" className="w-24 h-[270px]" aria-label={`T2108 ${clamped.toFixed(1)} percent`}>
          <defs>
            <linearGradient id="metalBacking" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="25%" stopColor="#0f172a" />
              <stop offset="75%" stopColor="#020617" />
              <stop offset="100%" stopColor="#1e293b" />
            </linearGradient>

            <linearGradient id="glassReflection" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="rgba(255,255,255,0.04)" />
              <stop offset="20%" stopColor="rgba(255,255,255,0.22)" />
              <stop offset="40%" stopColor="rgba(255,255,255,0)" />
              <stop offset="85%" stopColor="rgba(0,0,0,0.5)" />
              <stop offset="100%" stopColor="rgba(255,255,255,0.12)" />
            </linearGradient>

            <linearGradient id="mercuryRed" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#ef4444" />
              <stop offset="35%" stopColor="#fca5a5" />
              <stop offset="70%" stopColor="#dc2626" />
              <stop offset="100%" stopColor="#991b1b" />
            </linearGradient>
            <linearGradient id="mercuryGreen" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#10b981" />
              <stop offset="35%" stopColor="#a7f3d0" />
              <stop offset="70%" stopColor="#059669" />
              <stop offset="100%" stopColor="#065f46" />
            </linearGradient>
            <linearGradient id="mercurySilver" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#94a3b8" />
              <stop offset="35%" stopColor="#f1f5f9" />
              <stop offset="70%" stopColor="#64748b" />
              <stop offset="100%" stopColor="#334155" />
            </linearGradient>

            <radialGradient id="bulbRed" cx="35%" cy="35%" r="65%">
              <stop offset="0%" stopColor="#fca5a5" />
              <stop offset="45%" stopColor="#ef4444" />
              <stop offset="80%" stopColor="#991b1b" />
              <stop offset="100%" stopColor="#450a0a" />
            </radialGradient>
            <radialGradient id="bulbGreen" cx="35%" cy="35%" r="65%">
              <stop offset="0%" stopColor="#a7f3d0" />
              <stop offset="45%" stopColor="#10b981" />
              <stop offset="80%" stopColor="#065f46" />
              <stop offset="100%" stopColor="#022c22" />
            </radialGradient>
            <radialGradient id="bulbSilver" cx="35%" cy="35%" r="65%">
              <stop offset="0%" stopColor="#f8fafc" />
              <stop offset="45%" stopColor="#cbd5e1" />
              <stop offset="80%" stopColor="#475569" />
              <stop offset="100%" stopColor="#0f172a" />
            </radialGradient>

            <filter id="neonGlowRed" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="neonGlowGreen" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <rect x="2" y="2" width="86" height="276" rx="8" fill="url(#metalBacking)" stroke="#090d16" strokeWidth="2" />
          <rect x="5" y="5" width="80" height="270" rx="6" fill="none" stroke="#334155" strokeWidth="0.5" opacity="0.4" />

          <g fontFamily="monospace" fontSize="8" fontWeight="bold">
            <line x1="26" y1="30" x2="36" y2="30" stroke="#64748b" strokeWidth="1" />
            <text x="21" y="33" fill="#64748b" textAnchor="end">
              100
            </text>

            <line x1="24" y1="66" x2="36" y2="66" stroke="#ef4444" strokeWidth="1.2" />
            <text x="19" y="69" fill="#ef4444" textAnchor="end">
              80
            </text>

            <line x1="26" y1="102" x2="36" y2="102" stroke="#475569" strokeWidth="1" />
            <text x="21" y="105" fill="#475569" textAnchor="end">
              60
            </text>

            <line x1="26" y1="138" x2="36" y2="138" stroke="#475569" strokeWidth="1" />
            <text x="21" y="141" fill="#475569" textAnchor="end">
              40
            </text>

            <line x1="24" y1="174" x2="36" y2="174" stroke="#10b981" strokeWidth="1.2" />
            <text x="19" y="177" fill="#10b981" textAnchor="end">
              20
            </text>

            <line x1="26" y1="210" x2="36" y2="210" stroke="#64748b" strokeWidth="1" />
            <text x="21" y="213" fill="#64748b" textAnchor="end">
              0
            </text>
          </g>

          <g stroke="#334155" strokeWidth="0.5" opacity="0.7">
            <line x1="30" y1="48" x2="36" y2="48" />
            <line x1="30" y1="84" x2="36" y2="84" />
            <line x1="30" y1="120" x2="36" y2="120" />
            <line x1="30" y1="156" x2="36" y2="156" />
            <line x1="30" y1="192" x2="36" y2="192" />
          </g>

          <rect x="42" y="22" width="6" height="195" rx="3" fill="#020617" stroke="#1e293b" strokeWidth="0.5" />

          <rect
            x="43.5"
            y={mercuryY}
            width="3"
            height={Math.max(0, mercuryHeight)}
            rx="1"
            fill={`url(#${mercuryColorId})`}
            filter={glowFilterId}
            style={{ transition: "y 1.2s cubic-bezier(0.19, 1, 0.22, 1), height 1.2s cubic-bezier(0.19, 1, 0.22, 1)" }}
          />

          {mercuryHeight > 0 ? (
            <circle
              cx="45"
              cy={mercuryY}
              r="1.5"
              fill="#ffffff"
              opacity="0.8"
              style={{ transition: "cy 1.2s cubic-bezier(0.19, 1, 0.22, 1)" }}
            />
          ) : null}

          <rect x="42" y="22" width="6" height="195" rx="3" fill="url(#glassReflection)" pointerEvents="none" />

          <circle cx="45" cy="242" r="14" fill="#020617" stroke="#1e293b" strokeWidth="0.8" />
          <circle
            cx="45"
            cy="242"
            r="11.5"
            fill={`url(#${bulbColorId})`}
            filter={glowFilterId}
            style={{ transition: "fill 1.2s ease-in-out" }}
          />
          <circle cx="45" cy="242" r="11.5" fill="url(#glassReflection)" pointerEvents="none" />
          <circle cx="41.5" cy="238.5" r="3" fill="#ffffff" opacity="0.55" pointerEvents="none" />
        </svg>
      </div>

      <div className="text-center mt-3 z-10 font-mono">
        <span className={`text-2xl font-black tracking-tighter tabular-nums ${indicatorColor}`}>
          {clamped.toFixed(1)}%
        </span>
        {overbought ? (
          <div className="text-[8px] text-rose-400 font-bold uppercase tracking-widest mt-0.5 animate-pulse">
            Overbought
          </div>
        ) : oversold ? (
          <div className="text-[8px] text-emerald-400 font-bold uppercase tracking-widest mt-0.5 animate-pulse">
            Oversold
          </div>
        ) : (
          <div className="text-[8px] text-slate-500 uppercase tracking-widest mt-0.5">Neutral</div>
        )}
      </div>
    </div>
  );
}

type EquilibriumRailProps = {
  label: string;
  upVal: number;
  dnVal: number;
  upExtreme: boolean;
  dnExtreme: boolean;
};

function EquilibriumRail({ label, upVal, dnVal, upExtreme, dnExtreme }: EquilibriumRailProps) {
  const total = upVal + dnVal || 1;
  const upPercent = (upVal / total) * 100;

  return (
    <div className="bg-[#090d16]/30 border border-slate-900/40 rounded-lg p-3 flex flex-col gap-2 relative overflow-hidden">
      {dnExtreme ? (
        <div className="absolute inset-0 pointer-events-none opacity-[0.03] bg-[repeating-linear-gradient(45deg,#f43f5e,#f43f5e_10px,#000_10px,#000_20px)]" />
      ) : null}
      {upExtreme ? (
        <div className="absolute inset-0 pointer-events-none opacity-[0.03] bg-[repeating-linear-gradient(45deg,#10b981,#10b981_10px,#000_10px,#000_20px)]" />
      ) : null}

      <div className="flex justify-between items-center select-none">
        <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-slate-400">{label}</span>
        {dnExtreme ? (
          <span className="text-[8px] font-mono text-rose-400 font-bold bg-rose-950/50 px-1 rounded animate-pulse">
            CAPITULATION
          </span>
        ) : upExtreme ? (
          <span className="text-[8px] font-mono text-emerald-400 font-bold bg-emerald-950/50 px-1 rounded animate-pulse">
            CLIMAX
          </span>
        ) : (
          <span className="text-[8px] font-mono text-slate-600">BALANCED</span>
        )}
      </div>

      <div className="flex justify-between items-baseline font-mono select-none">
        <span
          className={`text-sm font-black transition-colors ${
            upExtreme ? "text-emerald-400 drop-shadow-[0_0_6px_rgba(16,185,129,0.3)]" : "text-slate-400"
          }`}
        >
          {upVal} <span className="text-[8px] font-medium text-slate-600">UP</span>
        </span>
        <span
          className={`text-sm font-black transition-colors ${
            dnExtreme ? "text-rose-400 drop-shadow-[0_0_6px_rgba(244,63,94,0.3)]" : "text-slate-400"
          }`}
        >
          {dnVal} <span className="text-[8px] font-medium text-slate-600">DN</span>
        </span>
      </div>

      <div className="relative w-full h-2.5 bg-slate-950 border border-slate-800/80 rounded-full flex items-center shadow-inner">
        <div className="absolute left-1/2 -translate-x-1/2 w-[2px] h-full bg-slate-700/50 z-10" />
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out opacity-30 ${
            upPercent > 50 ? "bg-emerald-500" : "bg-rose-500"
          }`}
          style={{ width: `${upPercent}%` }}
        />
        <div
          className={`absolute w-3 h-3 rounded-full border border-white/40 shadow-md transition-all duration-700 ease-out -translate-x-1/2 z-20 ${
            upPercent > 60
              ? "bg-emerald-400 shadow-[0_0_8px_#10b981]"
              : upPercent < 40
                ? "bg-rose-400 shadow-[0_0_8px_#f43f5e]"
                : "bg-slate-400"
          }`}
          style={{ left: `${upPercent}%` }}
        />
      </div>
    </div>
  );
}

export default function CockpitSection() {
  const [payload, setPayload] = useState<BreadthPayload | null>(null);
  const [terminalHealth, setTerminalHealth] = useState<TerminalHealth>("offline");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchJson<BreadthPayload>("/api/breadth?limit=60"),
      fetchJson<HealthReport>("/api/health?quick=1").catch(() => null),
    ])
      .then(([breadth, health]) => {
        setPayload(breadth);
        setTerminalHealth(resolveTerminalHealth(breadth, health));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const CHART_LOOKBACK_DAYS = SPARKLINE_LOOKBACK_DAYS;

  const chronologicalData = useMemo(() => {
    if (!payload?.rows) return [];
    return [...payload.rows].slice(0, CHART_LOOKBACK_DAYS).reverse();
  }, [payload]);

  const q25LineData = useMemo(
    () =>
      chronologicalData.map((row) => ({
        date: row.raw_date || row.date || "",
        up25: +(row.c5_num ?? 0),
        dn25: +(row.c6_num ?? 0),
      })),
    [chronologicalData],
  );

  if (loading) {
    return (
      <div className="bg-[#0b0f19] rounded-xl border border-slate-800 p-8 flex items-center justify-center min-h-[300px]">
        <div className="flex items-center gap-3 text-slate-500 font-mono text-sm">
          <Activity className="animate-spin" size={16} /> SYNCING STOCKBEE MATRIX...
        </div>
      </div>
    );
  }

  const latestRow: BreadthRow = (payload?.rows || [])[0] || {};

  const up4 = +(latestRow.c1_num ?? 0);
  const dn4 = +(latestRow.c2_num ?? 0);
  const ratio5 = +(latestRow.c3_num ?? 0);
  const ratio10 = +(latestRow.c4_num ?? 0);
  const up25q = +(latestRow.c5_num ?? 0);
  const dn25q = +(latestRow.c6_num ?? 0);
  const up25m = +(latestRow.c7_num ?? 0);
  const dn25m = +(latestRow.c8_num ?? 0);
  const up50m = +(latestRow.c9_num ?? 0);
  const dn50m = +(latestRow.c10_num ?? 0);
  const up13 = +(latestRow.c11_num ?? 0);
  const dn13 = +(latestRow.c12_num ?? 0);
  const t2108 = +(latestRow.c14_num ?? 0);

  const snapshotDate =
    latestRow.raw_date || latestRow.date || payload?.coverage?.last_date || "AWAITING DATA";
  const healthUi = HEALTH_UI[terminalHealth];
  const isBullishPhase = up25q > dn25q;

  return (
    <div className="space-y-6 mb-8 font-sans">
      <div className="flex flex-col md:flex-row justify-between items-end mb-6 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-black tracking-widest text-slate-100 flex items-center gap-2">
            <Target className="text-cyan-500" /> STOCKBEE TACTICAL RADAR
          </h1>
          <p className="text-[10px] text-slate-500 uppercase mt-1 font-mono">
            Exhaustion &amp; Divergence Detection System
            {payload?.coverage?.row_count ? ` · ${payload.coverage.row_count.toLocaleString()} rows` : ""}
          </p>
        </div>

        <div className="flex items-center gap-4 mt-4 md:mt-0 font-mono">
          <div className="text-right">
            <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">
              Latest Snapshot
            </div>
            <div className="text-sm font-mono font-bold text-slate-300">{snapshotDate}</div>
          </div>
          <div className={`flex items-center gap-2 border px-3 py-1.5 rounded-md ${healthUi.wrap}`}>
            <div
              className={`w-2 h-2 rounded-full ${healthUi.dot} ${healthUi.pulse ? "animate-pulse" : ""}`}
            />
            <span className={`text-[10px] font-mono font-bold uppercase tracking-widest ${healthUi.text}`}>
              {healthUi.label}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-stretch">
        {/* Primary — xl:col-span-7 */}
        <div className="xl:col-span-7 bg-[#0b0f19] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col gap-6">
          <div className="flex justify-between items-center border-b border-slate-800 pb-3 select-none">
            <h3 className="text-xs font-black text-slate-300 uppercase tracking-widest font-mono flex items-center gap-2">
              <Activity size={14} className="text-cyan-500" /> Primary Breadth Indicators
            </h3>
            <span className="text-[8px] font-mono text-slate-500 bg-slate-900 px-2 py-0.5 rounded">
              LONG &amp; SHORT MOMENTUM THRUSTS
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1">
            <div className="flex flex-col gap-4 justify-between">
              <div className="flex items-center gap-4">
                <div className="w-20 shrink-0 select-none">
                  <div className="text-[9px] font-mono text-slate-500 uppercase">10D Ratio</div>
                  <div
                    className={`text-base font-black font-mono ${ratio10 >= 2 ? "text-amber-400" : "text-slate-300"}`}
                  >
                    {ratio10.toFixed(2)}
                  </div>
                </div>
                <div className="flex-1 bg-slate-900/30 rounded border border-slate-800/40 p-1">
                  <MicroSparkline
                    data={chronologicalData}
                    dataKey="c4_num"
                    threshold={RATIO_SPARKLINE_THRESHOLD}
                    color="#fbbf24"
                  />
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="w-20 shrink-0 select-none">
                  <div className="text-[9px] font-mono text-slate-500 uppercase">5D Ratio</div>
                  <div
                    className={`text-base font-black font-mono ${ratio5 >= 2 ? "text-amber-400" : "text-slate-300"}`}
                  >
                    {ratio5.toFixed(2)}
                  </div>
                </div>
                <div className="flex-1 bg-slate-900/30 rounded border border-slate-800/40 p-1">
                  <MicroSparkline
                    data={chronologicalData}
                    dataKey="c3_num"
                    threshold={RATIO_SPARKLINE_THRESHOLD}
                    color="#fbbf24"
                  />
                </div>
              </div>

              <div className="flex items-center gap-4 pt-2 border-t border-slate-800/50">
                <div className="w-20 shrink-0 select-none">
                  <div className="text-[9px] font-mono text-emerald-500 font-bold uppercase">4% UP</div>
                  <div
                    className={`text-base font-black font-mono ${
                      up4 >= UP4_SPARKLINE_THRESHOLD ? "text-emerald-400" : "text-slate-300"
                    }`}
                  >
                    {up4}
                  </div>
                </div>
                <div className="flex-1 bg-slate-900/30 rounded border border-slate-800/40 p-1">
                  <MicroSparkline
                    data={chronologicalData}
                    dataKey="c1_num"
                    threshold={UP4_SPARKLINE_THRESHOLD}
                    color="#10b981"
                  />
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="w-20 shrink-0 select-none">
                  <div className="text-[9px] font-mono text-rose-500 font-bold uppercase">4% DN</div>
                  <div
                    className={`text-base font-black font-mono ${
                      dn4 >= DN4_SPARKLINE_THRESHOLD ? "text-rose-400" : "text-slate-300"
                    }`}
                  >
                    {dn4}
                  </div>
                </div>
                <div className="flex-1 bg-slate-900/30 rounded border border-slate-800/40 p-1">
                  <MicroSparkline
                    data={chronologicalData}
                    dataKey="c2_num"
                    threshold={DN4_SPARKLINE_THRESHOLD}
                    color="#f43f5e"
                  />
                </div>
              </div>
            </div>

            <div
              className={`rounded-lg border p-3 flex flex-col gap-2 transition-all duration-1000 ${
                isBullishPhase
                  ? "bg-emerald-950/10 border-emerald-900/40 shadow-[inset_0_0_15px_rgba(16,185,129,0.05)]"
                  : "bg-rose-950/10 border-rose-900/40 shadow-[inset_0_0_15px_rgba(244,63,94,0.05)]"
              }`}
            >
              <div className="flex justify-between items-center select-none">
                <div>
                  <span className="text-[9px] font-mono font-black text-slate-500 uppercase tracking-widest block">
                    Quarterly Momentum
                  </span>
                  <span
                    className={`text-xs font-mono font-black ${isBullishPhase ? "text-emerald-400" : "text-rose-400"}`}
                  >
                    {isBullishPhase ? "BULL RUNNING" : "BEAR RUNNING"}
                  </span>
                </div>
                <div className="text-right text-[10px] font-mono font-bold select-none">
                  <span className="text-emerald-400">{up25q}U</span>
                  <span className="text-slate-600 mx-1">/</span>
                  <span className="text-rose-400">{dn25q}D</span>
                </div>
              </div>

              <div className="flex-1 min-h-[110px] w-full bg-black/40 rounded border border-slate-900 overflow-hidden relative">
                <div
                  className="absolute inset-0 pointer-events-none opacity-[0.02]"
                  style={{
                    backgroundImage: isBullishPhase
                      ? "radial-gradient(#10b981 1px, transparent 1px)"
                      : "radial-gradient(#f43f5e 1px, transparent 1px)",
                    backgroundSize: "12px 12px",
                  }}
                />
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={q25LineData} margin={{ top: 10, right: 2, left: 2, bottom: 2 }}>
                    <YAxis domain={["auto", "auto"]} hide />
                    <defs>
                      <linearGradient id="colorUp" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={isBullishPhase ? 0.2 : 0.02} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="colorDn" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f43f5e" stopOpacity={!isBullishPhase ? 0.2 : 0.02} />
                        <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="up25"
                      stroke={isBullishPhase ? "#10b981" : "#334155"}
                      strokeWidth={isBullishPhase ? 2 : 1}
                      fillOpacity={1}
                      fill="url(#colorUp)"
                      isAnimationActive={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="dn25"
                      stroke={!isBullishPhase ? "#f43f5e" : "#334155"}
                      strokeWidth={!isBullishPhase ? 2 : 1}
                      fillOpacity={1}
                      fill="url(#colorDn)"
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>

        {/* Secondary — xl:col-span-3 */}
        <div className="xl:col-span-3 bg-[#0d1117] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col gap-4">
          <div className="flex justify-between items-center border-b border-slate-800 pb-3 select-none">
            <h3 className="text-xs font-black text-slate-300 uppercase tracking-widest font-mono flex items-center gap-2">
              <Zap size={14} className="text-amber-500" /> Tactical Indicators
            </h3>
            <span className="text-[8px] text-slate-600 font-mono uppercase">Equilibrium</span>
          </div>

          <div className="flex flex-col gap-3 justify-center flex-1">
            <EquilibriumRail
              label="13% / 34d Fast Swing"
              upVal={up13}
              dnVal={dn13}
              upExtreme={up13 >= 1500}
              dnExtreme={dn13 >= 1500}
            />
            <EquilibriumRail
              label="25% / Month Medium"
              upVal={up25m}
              dnVal={dn25m}
              upExtreme={up25m >= 400}
              dnExtreme={dn25m >= 400}
            />
            <EquilibriumRail
              label="50% / Month Exhaustion"
              upVal={up50m}
              dnVal={dn50m}
              upExtreme={up50m >= 15}
              dnExtreme={dn50m >= 15}
            />
          </div>
        </div>

        {/* T2108 — xl:col-span-2 */}
        <div className="xl:col-span-2">
          <CustomT2108Thermometer value={t2108} />
        </div>
      </div>
    </div>
  );
}
