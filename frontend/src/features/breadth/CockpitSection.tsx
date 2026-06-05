import { useState, useEffect } from 'react';
import { Target, Activity, Zap, Anchor, ShieldAlert, BarChart2 } from 'lucide-react';
import { fetchJson } from '../../lib/api';
import '../../styles/cockpit.css';

interface BreadthPayload {
  rows?: any[];
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

type TerminalHealth = 'healthy' | 'degraded' | 'offline';

const HEALTH_UI: Record<
  TerminalHealth,
  { label: string; wrap: string; text: string; dot: string; pulse: boolean }
> = {
  healthy: {
    label: 'System Healthy',
    wrap: 'bg-emerald-950/20 border-emerald-900/50',
    text: 'text-emerald-500',
    dot: 'bg-emerald-500 drop-shadow-[0_0_5px_rgba(16,185,129,0.8)]',
    pulse: true,
  },
  degraded: {
    label: 'Data Stale — Verify',
    wrap: 'bg-amber-950/20 border-amber-900/50',
    text: 'text-amber-500',
    dot: 'bg-amber-500 drop-shadow-[0_0_5px_rgba(245,158,11,0.8)]',
    pulse: true,
  },
  offline: {
    label: 'System Offline',
    wrap: 'bg-rose-950/20 border-rose-900/50',
    text: 'text-rose-500',
    dot: 'bg-rose-500',
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
  if (!health || health.status === 'error') return 'offline';
  const checks = health.checks || {};
  if (!checks.db?.ok) return 'offline';

  const latestDate = payload?.rows?.[0]?.date || payload?.rows?.[0]?.raw_date;
  const coverageLast = payload?.coverage?.last_date;
  if (!latestDate && !coverageLast) return 'degraded';

  if (health.status === 'degraded') return 'degraded';
  if (!checkPresent(checks.proxy) || !checkPresent(checks.breadth_source)) return 'degraded';
  return 'healthy';
}

export default function CockpitSection() {
  const [payload, setPayload] = useState<BreadthPayload | null>(null);
  const [terminalHealth, setTerminalHealth] = useState<TerminalHealth>('offline');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchJson<BreadthPayload>('/api/breadth?limit=10'),
      fetchJson<HealthReport>('/api/health?quick=1').catch(() => null),
    ])
      .then(([breadth, health]) => {
        setPayload(breadth);
        setTerminalHealth(resolveTerminalHealth(breadth, health));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-[#0b0f19] rounded-xl border border-slate-800 p-8 flex items-center justify-center min-h-[300px]">
        <div className="flex items-center gap-3 text-slate-500 font-mono text-sm">
          <Activity className="animate-spin" size={16} /> SYNCING STOCKBEE MATRIX...
        </div>
      </div>
    );
  }

  // ── 提取数据 ────────────────────────────────────────────────────────
  const latestRow: any = (payload?.rows || [])[0] || {};
  
  // Primary
  const up4 = +(latestRow.c1_num ?? 0);
  const dn4 = +(latestRow.c2_num ?? 0);
  const ratio5 = +(latestRow.c3_num ?? 0);
  const ratio10 = +(latestRow.c4_num ?? 0);
  const up25q = +(latestRow.c5_num ?? 0);
  const dn25q = +(latestRow.c6_num ?? 0);

  // Secondary
  const up25m = +(latestRow.c7_num ?? 0);
  const dn25m = +(latestRow.c8_num ?? 0);
  const up50m = +(latestRow.c9_num ?? 0);
  const dn50m = +(latestRow.c10_num ?? 0);
  const up13 = +(latestRow.c11_num ?? 0);
  const dn13 = +(latestRow.c12_num ?? 0);
  const t2108 = +(latestRow.c14_num ?? 0);

  // ── 逻辑判定引擎 ──────────────────────────────────────────────────────

  // 1. Quarter Phase (主基调)
  const isQuarterBull = up25q > dn25q;
  const quarterExtremeUp = up25q < 200; // Extremely bullish (Reversal)
  const quarterExtremeDn = dn25q < 200; // Extremely bearish (Top forming in 2-6 weeks)
  const _quarterWatchReversal = up25q < 500 && up25q >= 200;
  void _quarterWatchReversal;

  // 2. Daily 4% (日内压力)
  const getDailyStatus = (val: number, type: 'up' | 'dn') => {
    if (val >= 1000) return { label: 'EXTREME', color: type === 'up' ? 'text-emerald-400 bg-emerald-950/40 border-emerald-500' : 'text-rose-400 bg-rose-950/40 border-rose-500' };
    if (val >= 500) return { label: 'VERY HIGH', color: type === 'up' ? 'text-emerald-500 bg-emerald-950/20' : 'text-rose-500 bg-rose-950/20' };
    if (type === 'up' && val >= 300) return { label: 'HIGH', color: 'text-emerald-600' };
    return { label: 'NORMAL', color: 'text-slate-500' };
  };
  const up4Status = getDailyStatus(up4, 'up');
  const dn4Status = getDailyStatus(dn4, 'dn');

  // 3. Ratio 10D/5D (趋势推力)
  const getRatioStatus = (val: number) => {
    if (val >= 2.0) return { label: 'BULL THRUST (Long)', color: 'text-emerald-400 border-emerald-500/50 bg-emerald-950/30' };
    if (val <= 0.5) return { label: 'BEAR THRUST (Short)', color: 'text-rose-400 border-rose-500/50 bg-rose-950/30' };
    return { label: 'NEUTRAL', color: 'text-slate-500 border-slate-800' };
  };
  const ratio10Status = getRatioStatus(ratio10);
  const ratio5Status = getRatioStatus(ratio5);

  // 4. Secondary 50% Month (波段极值)
  const get50mStatus = (val: number, type: 'up' | 'dn') => {
    if (type === 'up') {
      if (val >= 20) return { label: 'BEARISH (Correction)', color: 'text-rose-400' };
      if (val < 3) return { label: 'BULLISH (Extreme Bearishness)', color: 'text-emerald-400' };
    } else {
      if (val >= 20) return { label: 'BEARISH (Reflex Rally)', color: 'text-amber-400' };
    }
    return { label: '-', color: 'text-slate-600' };
  };

  // 5. T2108 (情绪乖离)
  const getT2108Status = (val: number) => {
    if (val >= 80) return { label: 'OVERBOUGHT', color: 'text-rose-400 bg-rose-950/30 border-rose-500/50' };
    if (val <= 20) return { label: 'OVERSOLD', color: 'text-emerald-400 bg-emerald-950/30 border-emerald-500/50' };
    return { label: 'NEUTRAL', color: 'text-slate-500 border-transparent' };
  };
  const t2108Status = getT2108Status(t2108);

  // ── 辅助渲染组件 ──────────────────────────────────────────────────────
  const ProgressBar = ({ up, dn }: { up: number; dn: number }) => {
    const total = up + dn || 1;
    const upPct = (up / total) * 100;
    return (
      <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
        <div className="h-full bg-emerald-500" style={{ width: `${upPct}%` }} />
        <div className="h-full bg-rose-500" style={{ width: `${100 - upPct}%` }} />
      </div>
    );
  };

  const snapshotDate = latestRow.raw_date || latestRow.date || payload?.coverage?.last_date || 'AWAITING DATA';
  const healthUi = HEALTH_UI[terminalHealth];

  return (
    <div className="space-y-6 mb-8 font-sans">
      <div className="flex flex-col md:flex-row justify-between items-end mb-6 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-black tracking-widest text-slate-100 flex items-center gap-2">
            <Target className="text-cyan-500" /> STOCKBEE BREADTH TERMINAL
          </h1>
          <p className="text-[10px] text-slate-500 uppercase mt-1 font-mono">
            Data Source: Google Sheet Matrix • Automated Sync
            {payload?.coverage?.row_count ? ` • ${payload.coverage.row_count.toLocaleString()} rows` : ''}
          </p>
        </div>

        <div className="flex items-center gap-4 mt-4 md:mt-0">
          <div className="text-right">
            <div className="text-[10px] text-slate-500 font-mono uppercase tracking-widest">Latest Snapshot</div>
            <div className="text-sm font-mono font-bold text-slate-300">{snapshotDate}</div>
          </div>
          <div className={`flex items-center gap-2 border px-3 py-1.5 rounded-md ${healthUi.wrap}`}>
            <div
              className={`w-2 h-2 rounded-full ${healthUi.dot} ${healthUi.pulse ? 'animate-pulse' : ''}`}
            />
            <span className={`text-[10px] font-mono font-bold uppercase tracking-widest ${healthUi.text}`}>
              {healthUi.label}
            </span>
          </div>
        </div>
      </div>

      {/* ── 主基调 Banner (Quarter Phase) ── */}
      <div className={`rounded-xl border px-6 py-5 flex justify-between items-center ${isQuarterBull ? 'bg-emerald-950/20 border-emerald-900/50' : 'bg-rose-950/20 border-rose-900/50'}`}>
        <div className="flex items-center gap-4">
          <div className={`p-3 rounded-lg border ${isQuarterBull ? 'bg-emerald-900/30 border-emerald-500/30 text-emerald-400' : 'bg-rose-900/30 border-rose-500/30 text-rose-400'}`}>
            {isQuarterBull ? <Anchor size={24} /> : <ShieldAlert size={24} />}
          </div>
          <div>
            <div className="text-[10px] font-mono tracking-widest text-slate-400 uppercase mb-1">Primary Market Phase</div>
            <h2 className={`text-2xl font-black tracking-widest ${isQuarterBull ? 'text-emerald-400' : 'text-rose-400'}`}>
              {isQuarterBull ? 'BULLISH PHASE' : 'BEARISH PHASE'}
            </h2>
          </div>
        </div>
        <div className="text-right flex items-center gap-6">
          <div className="flex flex-col items-end">
            <span className="text-[10px] uppercase font-mono text-emerald-500">Up 25% Qtr</span>
            <span className={`text-xl font-mono font-black ${quarterExtremeUp ? 'text-amber-400 animate-pulse' : 'text-slate-200'}`}>
              {up25q}
              {quarterExtremeUp && <span className="text-[10px] ml-2 bg-amber-500/20 px-1 rounded">EXTREME</span>}
            </span>
          </div>
          <div className="w-px h-8 bg-slate-800" />
          <div className="flex flex-col items-start">
            <span className="text-[10px] uppercase font-mono text-rose-500">Down 25% Qtr</span>
            <span className={`text-xl font-mono font-black ${quarterExtremeDn ? 'text-amber-400 animate-pulse' : 'text-slate-200'}`}>
              {dn25q}
              {quarterExtremeDn && <span className="text-[10px] ml-2 bg-amber-500/20 px-1 rounded">EXTREME</span>}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* ================= PRIMARY INDICATORS ================= */}
        <div className="bg-[#0b0f19] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col gap-5">
          <h3 className="text-xs font-black text-slate-300 uppercase tracking-widest font-mono border-b border-slate-800 pb-2 flex items-center gap-2">
            <Target size={14} className="text-cyan-500" /> Primary Breadth Indicators
          </h3>

          {/* Daily 4% */}
          <div className="space-y-3">
            <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Daily Pressure (4% Plus/Down)</div>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-800/80">
                <div className="flex justify-between items-start mb-1">
                  <span className="text-emerald-500 font-bold text-sm">UP 4%</span>
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${up4Status.color}`}>{up4Status.label}</span>
                </div>
                <div className="text-2xl font-mono font-black text-slate-200">{up4}</div>
              </div>
              <div className="bg-slate-900/50 rounded-lg p-3 border border-slate-800/80">
                <div className="flex justify-between items-start mb-1">
                  <span className="text-rose-500 font-bold text-sm">DN 4%</span>
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${dn4Status.color}`}>{dn4Status.label}</span>
                </div>
                <div className="text-2xl font-mono font-black text-slate-200">{dn4}</div>
              </div>
            </div>
          </div>

          {/* Cumulative Ratio */}
          <div className="space-y-3 pt-2 border-t border-slate-800/50">
            <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">Cumulative Thrust Ratio</div>
            <div className="flex gap-4">
              <div className={`flex-1 rounded-lg p-3 border ${ratio10Status.color}`}>
                <div className="text-[10px] opacity-70 uppercase font-mono mb-1">10 Day Ratio</div>
                <div className="flex items-baseline justify-between">
                  <span className="text-2xl font-mono font-black">{ratio10.toFixed(2)}</span>
                  <span className="text-[9px] font-bold tracking-wider">{ratio10Status.label}</span>
                </div>
              </div>
              <div className={`flex-1 rounded-lg p-3 border ${ratio5Status.color}`}>
                <div className="text-[10px] opacity-70 uppercase font-mono mb-1">5 Day Ratio</div>
                <div className="flex items-baseline justify-between">
                  <span className="text-2xl font-mono font-black">{ratio5.toFixed(2)}</span>
                  <span className="text-[9px] font-bold tracking-wider">{ratio5Status.label}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ================= SECONDARY INDICATORS ================= */}
        <div className="bg-[#0b0f19] border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col gap-5">
          <h3 className="text-xs font-black text-slate-300 uppercase tracking-widest font-mono border-b border-slate-800 pb-2 flex items-center gap-2">
            <Zap size={14} className="text-amber-500" /> Secondary / Tactical Indicators
          </h3>

          <div className="grid grid-cols-2 gap-4">
            {/* Fast 34/13 Trend */}
            <div className="col-span-2 bg-slate-900/30 rounded-lg p-3 border border-slate-800">
              <div className="flex justify-between text-[10px] font-mono text-slate-500 uppercase mb-2">
                <span>34/13 Fast Trend</span>
                <span className={up13 > dn13 ? 'text-emerald-500' : 'text-rose-500'}>{up13 > dn13 ? 'BULL' : 'BEAR'}</span>
              </div>
              <ProgressBar up={up13} dn={dn13} />
              <div className="flex justify-between text-xs font-mono font-bold mt-1">
                <span className="text-emerald-400">{up13}</span>
                <span className="text-rose-400">{dn13}</span>
              </div>
            </div>

            {/* Monthly 25% */}
            <div className="bg-slate-900/30 rounded-lg p-3 border border-slate-800">
              <div className="text-[10px] font-mono text-slate-500 uppercase mb-2 text-center">Month 25%</div>
              <div className="flex justify-between px-2">
                <div className="text-center">
                  <div className="text-[9px] text-emerald-500/70">UP</div>
                  <div className="text-lg font-mono font-bold text-slate-300">{up25m}</div>
                </div>
                <div className="w-px bg-slate-800" />
                <div className="text-center">
                  <div className="text-[9px] text-rose-500/70">DN</div>
                  <div className="text-lg font-mono font-bold text-slate-300">{dn25m}</div>
                </div>
              </div>
            </div>

            {/* Monthly 50% */}
            <div className="bg-slate-900/30 rounded-lg p-3 border border-slate-800">
              <div className="text-[10px] font-mono text-slate-500 uppercase mb-2 text-center">Month 50% Extremes</div>
              <div className="flex justify-between px-2">
                <div className="text-center">
                  <div className="text-[9px] text-emerald-500/70 mb-0.5">UP</div>
                  <div className="text-lg font-mono font-bold text-slate-300 leading-none">{up50m}</div>
                  <div className={`text-[8px] font-bold mt-1 ${get50mStatus(up50m, 'up').color}`}>{get50mStatus(up50m, 'up').label}</div>
                </div>
                <div className="w-px bg-slate-800" />
                <div className="text-center">
                  <div className="text-[9px] text-rose-500/70 mb-0.5">DN</div>
                  <div className="text-lg font-mono font-bold text-slate-300 leading-none">{dn50m}</div>
                  <div className={`text-[8px] font-bold mt-1 ${get50mStatus(dn50m, 'dn').color}`}>{get50mStatus(dn50m, 'dn').label}</div>
                </div>
              </div>
            </div>
            
            {/* T2108 Alert */}
            <div className={`col-span-2 rounded-lg p-3 border flex justify-between items-center ${t2108Status.color}`}>
              <div className="flex items-center gap-2">
                <BarChart2 size={16} className="opacity-70" />
                <span className="text-[10px] font-mono uppercase tracking-widest opacity-80">T2108 Oscillator</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-bold tracking-widest">{t2108Status.label}</span>
                <span className="text-2xl font-mono font-black">{t2108}%</span>
              </div>
            </div>
            
          </div>
        </div>

      </div>
    </div>
  );
}
