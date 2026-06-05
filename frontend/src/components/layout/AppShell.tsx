import { useEffect } from "react";
import type { ReactNode } from "react";
import { Database } from "lucide-react";
import { IS_READONLY } from "../../lib/api";
import { TopNav } from "./TopNav";
import { TerminalHealthIndicator } from "./TerminalHealthIndicator";
import "../../styles/cockpit.css";

type AppShellProps = {
  title: string;
  source: string;
  children: ReactNode;
  mainClassName?: string;
};

export function AppShell({ title, source, children, mainClassName = "" }: AppShellProps) {
  useEffect(() => {
    if (!IS_READONLY) return;
    fetch(`${import.meta.env.BASE_URL}data/meta.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((meta) => {
        if (!meta?.exported_at) return;
        const el = document.getElementById("readonlyBanner");
        if (!el) return;
        const snap = meta.snapshot_date ? ` · data ${meta.snapshot_date}` : "";
        el.textContent = `Read-only snapshot · exported ${String(meta.exported_at).slice(0, 19).replace("T", " ")} UTC${snap}`;
      })
      .catch(() => {});
  }, []);

  return (
    <div
      className={`min-h-screen bg-[#050811] text-slate-200 font-sans selection:bg-cyan-900/50 ${mainClassName}`}
    >
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <header className="sticky top-0 z-50 bg-[#050811]/90 backdrop-blur-md border-b border-slate-800/80 shadow-sm">
        <div className="max-w-[1600px] mx-auto px-4 md:px-6 h-14 flex items-center justify-between gap-4">
          <TopNav />

          <div className="flex items-center gap-3 shrink-0">
            <div
              className="hidden md:flex items-center gap-1.5 text-[10px] text-slate-500 font-mono tracking-widest bg-slate-900/50 px-3 py-1 rounded-full border border-slate-800 max-w-[280px] truncate"
              title={source}
            >
              <Database size={12} className="opacity-70 shrink-0" />
              <span className="truncate">{source}</span>
            </div>
            <TerminalHealthIndicator />
          </div>
        </div>

        {IS_READONLY ? (
          <p
            className="text-center text-[10px] font-mono text-slate-500 border-t border-slate-800/60 py-1 bg-slate-900/30"
            id="readonlyBanner"
          >
            Read-only snapshot · refreshed by GitHub Actions after each US session
          </p>
        ) : null}
      </header>

      <h1 className="sr-only">{title}</h1>

      <main id="main-content" className="w-full">
        {children}
      </main>
    </div>
  );
}
