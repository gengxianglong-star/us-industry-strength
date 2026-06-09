import { AppShell } from "../../components/layout/AppShell";
import CockpitSection from "./CockpitSection";
import BreadthChartsSection from "./BreadthChartsSection";

export function BreadthPage() {
  return (
    <AppShell
      title="Market Breadth Terminal"
      source="Source: Stockbee Matrix Data Stream"
    >
      <div className="cockpit-preview max-w-[1600px] mx-auto px-4 md:px-6 py-6 space-y-6">
        <CockpitSection />
        <BreadthChartsSection />
      </div>
    </AppShell>
  );
}
