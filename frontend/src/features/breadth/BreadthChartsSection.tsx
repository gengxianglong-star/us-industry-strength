import { useState, useEffect, useMemo, type ReactNode } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ComposedChart,
} from 'recharts';
import { Activity, BarChart2, Filter } from 'lucide-react';
import { fetchJson } from '../../lib/api';
import '../../styles/cockpit.css';

interface BreadthPayload {
  rows?: any[];
}

const TIME_RANGES = [
  { label: '3M', days: 60 },
  { label: '6M', days: 120 },
  { label: '1Y', days: 252 },
  { label: '3Y', days: 756 },
  { label: 'ALL', days: 0 },
];

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="bg-[#0b0f19] border border-slate-800 rounded-xl p-5 flex flex-col shadow-lg min-h-[350px]">
      <div className="mb-4">
        <h3 className="text-sm font-black text-slate-300 uppercase tracking-widest font-mono">{title}</h3>
        <p className="text-[10px] font-mono text-slate-500 uppercase mt-1">{subtitle}</p>
      </div>
      <div className="flex-1 w-full relative min-h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function parseSpx(row: Record<string, unknown>): number | null {
  const num = row.c15_num;
  if (num != null && num !== '') {
    const parsed = Number(num);
    return Number.isFinite(parsed) ? parsed : null;
  }
  const raw = row.c15;
  if (raw == null || raw === '') return null;
  const parsed = Number(String(raw).replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

export default function BreadthChartsSection() {
  const [payload, setPayload] = useState<BreadthPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(252);

  useEffect(() => {
    fetchJson<BreadthPayload>('/api/breadth?limit=2000')
      .then((p) => {
        setPayload(p);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const chartData = useMemo(() => {
    if (!payload?.rows) return [];

    const sourceRows = timeRange === 0 ? payload.rows : payload.rows.slice(0, timeRange);
    return [...sourceRows].reverse().map((r) => ({
      date: r.raw_date || r.date,
      up4: +(r.c1_num ?? 0),
      dn4: +(r.c2_num ?? 0),
      ratio5: +(r.c3_num ?? 0),
      ratio10: +(r.c4_num ?? 0),
      up25q: +(r.c5_num ?? 0),
      dn25q: +(r.c6_num ?? 0),
      up25m: +(r.c7_num ?? 0),
      dn25m: +(r.c8_num ?? 0),
      up50m: +(r.c9_num ?? 0),
      dn50m: +(r.c10_num ?? 0),
      up13: +(r.c11_num ?? 0),
      dn13: +(r.c12_num ?? 0),
      t2108: +(r.c14_num ?? 0),
      spx: parseSpx(r),
    }));
  }, [payload, timeRange]);

  const customTooltipStyle = {
    backgroundColor: '#0f172a',
    borderColor: '#1e293b',
    color: '#f1f5f9',
    fontFamily: 'monospace',
    fontSize: '12px',
    borderRadius: '8px',
    boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
  };

  if (loading) {
    return (
      <div className="bg-[#0b0f19] rounded-xl border border-slate-800 p-8 flex items-center justify-center h-[500px] mt-6">
        <div className="flex items-center gap-3 text-slate-500 font-mono text-sm">
          <Activity className="animate-spin" size={16} /> RENDERING HISTORICAL CHARTS...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 font-sans mt-8 border-t border-slate-800/50 pt-8">
      <div className="flex flex-col md:flex-row justify-between items-center bg-[#090e1a] p-4 rounded-xl border border-slate-800">
        <h2 className="text-lg font-black text-slate-200 uppercase tracking-widest flex items-center gap-2 mb-4 md:mb-0">
          <BarChart2 className="text-cyan-500" /> Historical Breadth Projection
        </h2>

        <div className="flex items-center gap-2 bg-slate-900 p-1 rounded-lg border border-slate-800">
          <Filter size={14} className="text-slate-500 ml-2" />
          {TIME_RANGES.map((range) => (
            <button
              key={range.label}
              type="button"
              onClick={() => setTimeRange(range.days)}
              className={`px-3 py-1 text-xs font-mono font-bold rounded-md transition-all ${
                timeRange === range.days
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <ChartCard
          title="Daily Pressure (Up 4% vs Down 4%)"
          subtitle="> 500 = Very High Pressure | > 1000 = Extreme (Reversals)"
        >
          <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} minTickGap={30} />
            <YAxis stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} />
            <Tooltip contentStyle={customTooltipStyle} />
            <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }} />
            <ReferenceLine
              y={1000}
              stroke="#f43f5e"
              strokeDasharray="3 3"
              opacity={0.5}
              label={{ value: 'EXTREME', position: 'insideTopLeft', fill: '#f43f5e', fontSize: 10 }}
            />
            <ReferenceLine y={500} stroke="#fbbf24" strokeDasharray="3 3" opacity={0.5} />
            <ReferenceLine y={300} stroke="#475569" strokeDasharray="3 3" opacity={0.5} />
            <Line type="monotone" dataKey="up4" name="Up 4%" stroke="#10b981" strokeWidth={1.5} dot={false} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="dn4" name="Down 4%" stroke="#e11d48" strokeWidth={1.5} dot={false} activeDot={{ r: 4 }} />
          </LineChart>
        </ChartCard>

        <ChartCard
          title="Cumulative Thrust & T2108 Extremes"
          subtitle="10D > 2.0 = Bull Thrust | T2108 > 80 = Overbought"
        >
          <ComposedChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} minTickGap={30} />
            <YAxis yAxisId="left" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} domain={[0, 'auto']} />
            <YAxis yAxisId="right" orientation="right" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} domain={[0, 100]} />
            <Tooltip contentStyle={customTooltipStyle} />
            <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }} />
            <ReferenceLine
              y={2.0}
              yAxisId="left"
              stroke="#10b981"
              strokeDasharray="3 3"
              opacity={0.5}
              label={{ value: 'BULL THRUST (2.0)', position: 'insideTopLeft', fill: '#10b981', fontSize: 9 }}
            />
            <ReferenceLine
              y={0.5}
              yAxisId="left"
              stroke="#e11d48"
              strokeDasharray="3 3"
              opacity={0.5}
              label={{ value: 'BEAR THRUST (0.5)', position: 'insideBottomLeft', fill: '#e11d48', fontSize: 9 }}
            />
            <ReferenceLine y={80} yAxisId="right" stroke="#f59e0b" strokeDasharray="3 3" opacity={0.3} />
            <ReferenceLine y={20} yAxisId="right" stroke="#0ea5e9" strokeDasharray="3 3" opacity={0.3} />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="ratio5"
              name="5 Day Ratio (Fast)"
              stroke="#2dd4bf"
              strokeWidth={1}
              strokeDasharray="3 3"
              dot={false}
              opacity={0.6}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="ratio10"
              name="10 Day Ratio"
              stroke="#8b5cf6"
              strokeWidth={2.5}
              dot={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="t2108"
              name="T2108 (%)"
              stroke="#f59e0b"
              strokeWidth={1}
              dot={false}
              opacity={0.8}
            />
          </ComposedChart>
        </ChartCard>

        <ChartCard
          title="Primary Phase (Up 25% Qtr vs Down 25% Qtr)"
          subtitle="< 200 = Extreme Reversal Zones"
        >
          <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} minTickGap={30} />
            <YAxis stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} />
            <Tooltip contentStyle={customTooltipStyle} />
            <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }} />
            <ReferenceLine
              y={200}
              stroke="#fbbf24"
              strokeDasharray="3 3"
              opacity={0.7}
              label={{ value: 'EXTREME REVERSAL (<200)', position: 'insideTopLeft', fill: '#fbbf24', fontSize: 10 }}
            />
            <Line type="monotone" dataKey="up25q" name="Up 25% Quarter" stroke="#10b981" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="dn25q" name="Down 25% Quarter" stroke="#e11d48" strokeWidth={2} dot={false} strokeDasharray="4 4" />
          </LineChart>
        </ChartCard>

        <ChartCard
          title="34/13 Fast Engine & SPX Overlay"
          subtitle="Fast trend changes compared against S&P 500"
        >
          <ComposedChart data={chartData} margin={{ top: 5, right: 5, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} minTickGap={30} />
            <YAxis yAxisId="left" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} />
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#0ea5e9"
              tick={{ fontSize: 10, fill: '#0ea5e9' }}
              domain={['dataMin - 100', 'dataMax + 100']}
            />
            <Tooltip contentStyle={customTooltipStyle} />
            <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }} />
            <Line yAxisId="right" type="monotone" dataKey="spx" name="S&P 500" stroke="#0ea5e9" strokeWidth={2} dot={false} opacity={0.5} connectNulls />
            <Line yAxisId="left" type="stepAfter" dataKey="up13" name="Up 13% (34D)" stroke="#10b981" strokeWidth={1.5} dot={false} />
            <Line
              yAxisId="left"
              type="stepAfter"
              dataKey="dn13"
              name="Down 13% (34D)"
              stroke="#e11d48"
              strokeWidth={1.5}
              dot={false}
              strokeDasharray="4 4"
            />
          </ComposedChart>
        </ChartCard>

        <ChartCard
          title="Monthly Rotation (Up 25% M vs Down 25% M)"
          subtitle="Near-term leadership confirmation"
        >
          <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} minTickGap={30} />
            <YAxis stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} />
            <Tooltip contentStyle={customTooltipStyle} />
            <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }} />
            <Line type="monotone" dataKey="up25m" name="Up 25% Month" stroke="#10b981" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="dn25m" name="Down 25% Month" stroke="#e11d48" strokeWidth={1.5} dot={false} />
          </LineChart>
        </ChartCard>

        <ChartCard
          title="Month 50% Extremes"
          subtitle=">= 20 often marks reflex rallies / correction pockets"
        >
          <LineChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} minTickGap={30} />
            <YAxis stroke="#475569" tick={{ fontSize: 10, fill: '#475569' }} />
            <Tooltip contentStyle={customTooltipStyle} />
            <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace' }} />
            <ReferenceLine y={20} stroke="#fbbf24" strokeDasharray="3 3" opacity={0.6} label={{ value: 'EXTREME (20)', position: 'insideTopLeft', fill: '#fbbf24', fontSize: 10 }} />
            <Line type="monotone" dataKey="up50m" name="Up 50% Month" stroke="#10b981" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="dn50m" name="Down 50% Month" stroke="#e11d48" strokeWidth={1.5} dot={false} />
          </LineChart>
        </ChartCard>
      </div>
    </div>
  );
}
