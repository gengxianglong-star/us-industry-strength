import { useEffect } from "react";
import type { ReactNode } from "react";
import { IS_READONLY } from "../../lib/api";
import { TopNav } from "./TopNav";
import { HealthBadge } from "./HealthBadge";

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
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <TopNav />
      <header className="page-header page-header-minimal">
        <div>
          <h1 className="sr-only">{title}</h1>
          <p className="page-source">{source}</p>
          {IS_READONLY ? (
            <p className="readonly-banner" id="readonlyBanner">
              Read-only snapshot · refreshed by GitHub Actions after each US session
            </p>
          ) : null}
        </div>
        <div className="header-actions">
          <HealthBadge />
        </div>
      </header>
      <main id="main-content" className={mainClassName}>
        {children}
      </main>
    </>
  );
}
