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
            <p className="readonly-banner">Read-only snapshot · refreshed by GitHub Actions after each US session</p>
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
