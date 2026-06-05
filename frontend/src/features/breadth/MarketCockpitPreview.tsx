import { useState } from 'react';
import { Rocket, AlertTriangle, Crosshair, Thermometer, BarChart2, Table, Eye } from 'lucide-react';
import '../../styles/cockpit.css';

// === 1. 更加硬核的量化数据源 (包含34D趋势历史与极值状态) ===
const INITIAL_DATA = {
  quarter: { percent: 62.8, isBull: true },
  monthly: { percent: 58.2, isBull: true },
  engine34D: {
    percent: 71.5,
    isBull: true,
    history: [42, 45, 41, 48, 52, 58, 55, 61, 64, 62, 68, 71.5]
  },
  cross5_10: { value: 2.65, isOverextended: true },
  t2108: { value: 84.5, isExtreme: true, status: 'CLIMAX OVERBOUGHT' },

  percentiles: [
    { label: 'Up 4% Daily Counts', value: 153, pct: 57.4 },
    { label: 'Down 4% Daily Counts', value: 431, pct: 93.1 },
    { label: 'Up 25% Quarter Counts', value: 1469, pct: 84.0 },
    { label: 'T2108 (% > 40MA)', value: 84.5, pct: 91.2 },
  ],
  gridRows: [
    { date: '2026-06-03', up4: 153, dn4: 431, ratio10d: 1.91, t2108: '84.5%', m34d: '71.5%', status: 'Climax' },
    { date: '2026-06-02', up4: 310, dn4: 85, ratio10d: 1.85, t2108: '79.2%', m34d: '68.0%', status: 'Bullish' },
    { date: '2026-06-01', up4: 285, dn4: 110, ratio10d: 1.72, t2108: '76.4%', m34d: '64.2%', status: 'Bullish' },
    { date: '2025-05-29', up4: 415, dn4: 65, ratio10d: 1.68, t2108: '74.1%', m34d: '62.0%', status: 'Bullish' },
    { date: '2025-05-28', up4: 190, dn4: 210, ratio10d: 1.45, t2108: '69.8%', m34d: '58.5%', status: 'Normal' },
  ]
};

// === 2. 左侧环形仪表盘组件 ===
function CircularGauge({ percent, title, isBull }: { percent: number; title: string; isBull: boolean }) {
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percent / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center p-3 bg-slate-900/40 rounded-xl border border-slate-800/80">
      <div className="relative w-20 h-20 flex items-center justify-center">
        <svg className="w-full h-full transform -rotate-90">
          <circle cx="40" cy="40" r={radius} className="stroke-slate-800/80" strokeWidth="5" fill="transparent" />
          <circle
            cx="40" cy="40" r={radius}
            className={`transition-all duration-1000 ${isBull ? 'stroke-emerald-500 shadow-lg' : 'stroke-rose-500'}`}
            strokeWidth="5" fill="transparent"
            strokeDasharray={circumference} strokeDashoffset={strokeDashoffset} strokeLinecap="round"
          />
        </svg>
        <div className="absolute text-center">
          <span className="text-base font-black font-mono text-slate-100 tracking-tighter">{percent}%</span>
        </div>
      </div>
      <span className="text-[10px] font-bold text-slate-500 mt-2 tracking-wider text-center uppercase">{title}</span>
    </div>
  );
}

export default function CompleteMarketDesk() {
  const [data] = useState(INITIAL_DATA);
  const [activeTab, setActiveTab] = useState<'grid' | 'percentile'>('grid');

  // SVG 趋势图路径生成器
  const generateSvgPath = (history: number[]) => {
    const width = 360;
    const height = 65;
    const maxVal = 100;
    const step = width / (history.length - 1);

    const points = history.map((val, index) => {
      const x = index * step;
      const y = height - (val / maxVal) * height + 5;
      return `${x},${y}`;
    });

    return {
      linePath: `M ${points.join(' L ')}`,
      areaPath: `M 0,${height} L ${points.join(' L ')} L ${width},${height} Z`
    };
  };

  const { linePath, areaPath } = generateSvgPath(data.engine34D.history);

  return (
    <div className="cockpit-preview min-h-screen bg-[#050811] text-slate-200 p-5 font-sans antialiased selection:bg-red-900">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* ================= HEADER ================= */}
        <header className="flex justify-between items-center border-b border-slate-900 pb-3">
          <div>
            <h1 className="text-xl font-black tracking-wider text-slate-100 flex items-center gap-2">
              <Crosshair className="text-cyan-500" size={20} /> STOCKBEE MARKET HEALTH DASHBOARD
            </h1>
            <p className="text-[10px] text-slate-500 uppercase tracking-widest font-mono mt-0.5">Top-Down Decision Framework & Integrated Data Matrix</p>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 px-3 py-1 rounded-md text-right text-[10px] font-mono text-slate-400">
            STATUS: <span className="text-red-400 font-bold animate-pulse">CLIMAX OVERHEAD RISK</span>
          </div>
        </header>

        {/* ================= 1. GLOBAL TEXT WORKFLOW BANNER ================= */}
        <div className="rounded-xl border border-red-500/30 bg-gradient-to-r from-red-950/40 to-slate-900/90 shadow-xl shadow-red-950/10">
          <div className="px-5 py-4 flex flex-col md:flex-row justify-between items-center gap-4 bg-black/30 backdrop-blur-md">
            <div className="flex items-center gap-3.5">
              <div className="bg-red-500/10 p-2.5 rounded-xl border border-red-500/20 text-red-400 animate-pulse">
                <AlertTriangle size={22} />
              </div>
              <div>
                <h2 className="text-lg font-black uppercase tracking-widest text-red-400 flex items-center gap-2">
                  CLIMAX OVERBOUGHT / 极度狂热预警
                </h2>
                <p className="text-slate-400 text-xs mt-0.5">
                  <span className="text-amber-400 font-bold">KQ Rule Alignment:</span> 34D引擎处于高位 ({data.engine34D.percent}%)，但 T2108 飙升至 {data.t2108.value}% 进入极度超买。**严禁执行任何新多头VCP突破开仓**，全面转入保护利润阶段，密切凝视抛物线做空机会。
                </p>
              </div>
            </div>
            <div className="bg-black/60 px-4 py-2.5 rounded-xl border border-slate-800 flex flex-col items-center flex-shrink-0">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">Max Risk Exposure</span>
              <span className="text-red-400 font-mono text-lg font-black">20% LIMIT</span>
            </div>
          </div>
        </div>

        {/* ================= 2. THE THREE-COLUMN COCKPIT ================= */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">

          {/* 【左列】Macro Base */}
          <div className="col-span-1 bg-[#090e1a] rounded-xl border border-slate-800/80 p-4 flex flex-col shadow-lg">
            <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3 pb-1.5 border-b border-slate-800/60 font-mono">Macro Buffer Bases</h3>
            <div className="grid grid-cols-2 gap-2 flex-1 items-center">
              <CircularGauge percent={data.quarter.percent} title="Quarter (Up25%Q)" isBull={data.quarter.isBull} />
              <CircularGauge percent={data.monthly.percent} title="Monthly (Up25%M)" isBull={data.monthly.isBull} />
            </div>
          </div>

          {/* 【中核心】Momentum Engine */}
          <div className="col-span-1 lg:col-span-2 bg-[#080d17] border-2 border-cyan-500/40 rounded-xl p-5 flex flex-col shadow-2xl relative overflow-hidden">
            <div className="flex justify-between items-center mb-2 relative z-10">
              <h3 className="text-xs font-black text-cyan-400 uppercase tracking-widest font-mono flex items-center gap-1.5">
                <Rocket size={14} className="text-cyan-400 animate-bounce" /> Momentum Engine (34D Lead)
              </h3>
              <span className="text-[9px] font-mono bg-cyan-950 text-cyan-400 border border-cyan-500/30 px-2 py-0.5 rounded font-bold">
                LEADING INDICATOR
              </span>
            </div>

            <div className="grid grid-cols-3 gap-4 items-center flex-1 relative z-10">
              <div className="col-span-1">
                <div className="text-slate-500 text-[10px] font-mono uppercase tracking-wider">Up13%/34D</div>
                <div className="text-4xl font-black text-slate-100 font-mono tracking-tighter mt-1">{data.engine34D.percent}%</div>
                <span className="inline-block mt-2 text-[9px] font-black bg-emerald-950 text-emerald-400 px-1.5 py-0.5 rounded">
                  ACCELERATING
                </span>
              </div>

              <div className="col-span-2 flex flex-col justify-end h-full pt-2">
                <div className="relative w-full h-[70px]">
                  <svg className="w-full h-full" viewBox="0 0 360 75" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25" />
                        <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>
                    <path d={areaPath} fill="url(#chartGradient)" />
                    <path d={linePath} fill="none" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" className="drop-shadow-[0_0_6px_rgba(34,211,238,0.6)]" />
                  </svg>
                </div>
                <div className="flex justify-between text-[8px] font-mono text-slate-600 mt-1 uppercase tracking-widest">
                  <span>34 Days Ago</span>
                  <span>Current Snapshot</span>
                </div>
              </div>
            </div>
          </div>

          {/* 【右列】Tactical Triggers */}
          <div className="col-span-1 bg-[#090e1a] rounded-xl border border-slate-800/80 p-4 flex flex-col shadow-lg justify-between">
            <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 pb-1.5 border-b border-slate-800/60 font-mono">Tactical Triggers</h3>
            <div className="space-y-3 flex-1 flex flex-col justify-center">

              <div className={`p-2 rounded-lg border flex justify-between items-center transition-all ${data.cross5_10.isOverextended ? 'bg-amber-950/30 border-amber-500/40 shadow-[0_0_10px_rgba(245,158,11,0.1)]' : 'bg-slate-950/40 border-slate-900'}`}>
                <div>
                  <div className="text-[9px] text-slate-500 font-mono uppercase tracking-wider">5-10D Cross</div>
                  <span className={`text-base font-mono font-black ${data.cross5_10.isOverextended ? 'text-amber-400' : 'text-slate-200'}`}>{data.cross5_10.value}</span>
                </div>
                {data.cross5_10.isOverextended && (
                  <span className="text-[8px] font-mono font-black bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded tracking-tighter animate-pulse">
                    OVEREXTENDED
                  </span>
                )}
              </div>

              <div className={`p-2.5 rounded-lg border transition-all duration-500 ${data.t2108.isExtreme ? 'bg-red-950/50 border-red-500/60 shadow-[0_0_15px_rgba(239,68,68,0.3)] animate-pulse' : 'bg-slate-950/40 border-slate-900'}`}>
                <div className="flex justify-between items-center mb-0.5">
                  <div className="text-[9px] text-red-400 font-mono uppercase tracking-widest flex items-center gap-0.5">
                    <Thermometer size={10} className="text-red-400" /> T2108 OVERBOUGHT
                  </div>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-2xl font-mono font-black text-red-400 tracking-tighter">{data.t2108.value}%</span>
                  <span className="text-[8px] font-black bg-red-500 text-white px-1 rounded tracking-widest scale-90">CRITICAL</span>
                </div>
              </div>

            </div>
          </div>
        </div>

        {/* ================= 3. BOTTOM MATRIX ================= */}
        <div className="bg-[#080c14] border border-slate-800 rounded-xl p-5 shadow-2xl space-y-6">

          <div className="flex justify-between items-center border-b border-slate-800 pb-2">
            <div className="flex gap-4">
              <button
                onClick={() => setActiveTab('grid')}
                className={`text-xs font-black uppercase tracking-wider flex items-center gap-1.5 pb-2 border-b-2 transition-all ${activeTab === 'grid' ? 'border-cyan-500 text-cyan-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
              >
                <Table size={13} /> Historical Breadth Stream (数据流)
              </button>
              <button
                onClick={() => setActiveTab('percentile')}
                className={`text-xs font-black uppercase tracking-wider flex items-center gap-1.5 pb-2 border-b-2 transition-all ${activeTab === 'percentile' ? 'border-cyan-500 text-cyan-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
              >
                <BarChart2 size={13} /> Historical Percentiles (百分位分布)
              </button>
            </div>
            <span className="text-[9px] font-mono text-slate-600 uppercase tracking-widest">Data pool updated: Read-Only Archive</span>
          </div>

          {activeTab === 'grid' && (
            <div className="overflow-x-auto rounded-lg border border-slate-900 shadow-inner">
              <table className="w-full text-left border-collapse font-mono text-xs text-slate-400">
                <thead>
                  <tr className="bg-slate-950 text-slate-500 text-[10px] uppercase tracking-widest border-b border-slate-800">
                    <th className="p-3">Data Date</th>
                    <th className="p-3 text-emerald-400">Up 4% Daily</th>
                    <th className="p-3 text-rose-400">Down 4% Daily</th>
                    <th className="p-3 text-indigo-400">10-Day Ratio</th>
                    <th className="p-3 text-red-400">T2108 Indicator</th>
                    <th className="p-3 text-cyan-400">34-Day Engine</th>
                    <th className="p-3 text-right">System Regime</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-900/50">
                  {data.gridRows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-900/40 transition-colors group">
                      <td className="p-3 text-slate-300 font-bold">{row.date}</td>
                      <td className="p-3 text-emerald-500 font-bold">{row.up4}</td>
                      <td className="p-3 text-rose-500">{row.dn4}</td>
                      <td className="p-3 text-indigo-300">{row.ratio10d}</td>
                      <td className={`p-3 font-bold ${idx === 0 ? 'text-red-400 bg-red-950/10' : 'text-slate-400'}`}>{row.t2108}</td>
                      <td className="p-3 text-cyan-400 font-medium">{row.m34d}</td>
                      <td className="p-3 text-right">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${row.status === 'Climax' ? 'bg-red-950 text-red-400 border border-red-800/40' : 'bg-slate-900 text-slate-400'}`}>
                          {row.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === 'percentile' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-2">
              {data.percentiles.map((p, idx) => (
                <div key={idx} className="bg-slate-950/50 p-4 rounded-xl border border-slate-900 shadow-inner space-y-2">
                  <div className="flex justify-between items-baseline">
                    <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{p.label}</span>
                    <div className="space-x-2 font-mono">
                      <span className="text-sm font-black text-slate-200">{p.value}</span>
                      <span className="text-[10px] text-cyan-400 bg-cyan-950/50 border border-cyan-800/30 px-1.5 py-0.5 rounded">{p.pct}th Pct</span>
                    </div>
                  </div>
                  <div className="relative pt-3 pb-1">
                    <div className="h-2 w-full bg-slate-800 rounded-full flex overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-emerald-600/40 via-yellow-500/40 to-red-600/40" style={{ width: '100%' }} />
                    </div>
                    <div
                      className="absolute top-1.5 transform -translate-x-1/2 flex flex-col items-center transition-all duration-1000"
                      style={{ left: `${p.pct}%` }}
                    >
                      <div className="w-0 h-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-t-[6px] border-t-cyan-400 drop-shadow-[0_0_3px_rgba(34,211,238,0.8)]" />
                    </div>
                    <div className="flex justify-between text-[8px] font-mono text-slate-600 mt-1 uppercase">
                      <span>Low Extreme</span>
                      <span>Mid</span>
                      <span>High Extreme</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="bg-slate-950/60 rounded-xl border border-slate-900 p-4 relative overflow-hidden min-h-[160px] flex flex-col justify-between">
            <div className="flex justify-between items-center border-b border-slate-900 pb-2">
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest font-mono flex items-center gap-1.5">
                <Eye size={12} className="text-indigo-400" /> Primary Multi-Pane Chart Overlay (主图叠加广度映射)
              </span>
              <span className="text-[9px] font-mono bg-slate-900 px-2 py-0.5 rounded border border-slate-800 text-slate-500">SPY / QQQ Core Correlation</span>
            </div>
            <div className="flex-1 flex flex-col justify-center items-center opacity-30 my-4 space-y-2">
              <div className="w-full h-8 flex items-end justify-center gap-1">
                {[40, 25, 45, 60, 55, 70, 85, 90, 80, 95, 110, 100, 120, 135, 125, 140].map((h, i) => (
                  <div key={i} className={`w-3 rounded-t-sm ${i > 12 ? 'bg-red-500' : 'bg-emerald-500'}`} style={{ height: `${h / 2}px` }} />
                ))}
              </div>
              <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest text-center">
                Interactive Charting Layer Active • Hover rows in Data Stream above to overlay historical percentile bands
              </p>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
