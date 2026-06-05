import { NavLink } from "react-router-dom";
import { BarChart2, Crosshair, TrendingUp } from "lucide-react";

const activeClass =
  "flex items-center gap-2 px-4 py-1.5 bg-slate-800/80 text-slate-100 rounded-md border border-slate-700 shadow-inner text-sm font-bold tracking-wide transition-colors";
const inactiveClass =
  "flex items-center gap-2 px-4 py-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-900/50 rounded-md transition-colors text-sm font-semibold tracking-wide";

export function TopNav() {
  return (
    <nav className="flex items-center gap-2" aria-label="Main navigation">
      <NavLink
        to="/terminal"
        end
        className={({ isActive }) => (isActive ? activeClass : inactiveClass)}
      >
        <Crosshair size={16} className="text-emerald-500" />
        <span>Quant Terminal</span>
      </NavLink>
      <NavLink
        to="/breadth"
        className={({ isActive }) => (isActive ? activeClass : inactiveClass)}
      >
        <BarChart2 size={16} className="text-cyan-500" />
        <span>Market Breadth</span>
      </NavLink>
      <NavLink
        to="/strong"
        className={({ isActive }) => (isActive ? activeClass : inactiveClass)}
      >
        <TrendingUp size={16} />
        <span>Strong Industry</span>
      </NavLink>
    </nav>
  );
}
