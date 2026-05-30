import { useEffect, useRef } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { IS_READONLY } from "../../lib/api";
import { mountBreadthController } from "./breadthController";

export function BreadthPage() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!rootRef.current) return;
    const controller = mountBreadthController(rootRef.current);
    return () => controller.destroy();
  }, []);

  return (
    <AppShell
      title="Market Breadth"
      source="Source: Stockbee Market Monitor (Google Sheet)"
      mainClassName="breadth-main"
    >
      <div ref={rootRef}>
        <section className="panel">
          <div className="panel-header-row">
            <h2>Market Cockpit</h2>
            <span className="hint cockpit-link-hint">Click a card to highlight its chart</span>
            <div className="sync-actions">
              <span id="coverageInline" className="hint" />
              <span id="syncProgressText" className="hint">
                Auto-sync · read-only
              </span>
            </div>
          </div>
          <div id="breadthStatusCards" className="breadth-status-grid" />
          <details className="cockpit-help-panel">
            <summary>Cockpit Rules</summary>
            <div id="cockpitHelpContent" className="cockpit-help-grid" />
          </details>
        </section>

        <section className="panel">
          <h2>Historical Percentiles</h2>
          <div id="breadthPercentileCards" className="breadth-percentile-grid" />
        </section>

        <section className="panel">
          <div className="panel-header-row">
            <h2>Breadth Overview</h2>
            <span id="breadthMeta" className="hint" />
          </div>
          <p className="hint">
            Scan definitions:{" "}
            <a
              id="explainLink"
              className="industry-link"
              target="_blank"
              rel="noreferrer"
              href="https://stockbee.blogspot.com/2022/12/market-monitor-scans.html"
            >
              Market Monitor Scans
            </a>
          </p>
          <div className="breadth-table-wrap">
            <table id="breadthTable">
              <thead />
              <tbody />
            </table>
          </div>
        </section>

        <section className="panel chart-panel">
          <div className="panel-header-row">
            <h2>Breadth Charts</h2>
            <div className="chart-header-actions">
              <div className="chart-linkage-control" id="chartRangeGroup">
                <button type="button" data-days="90">
                  3M
                </button>
                <button type="button" data-days="180">
                  6M
                </button>
                <button type="button" data-days="365" className="active">
                  1Y
                </button>
                <button type="button" data-days="1095">
                  3Y
                </button>
                <button type="button" data-days="1825">
                  5Y
                </button>
                <button type="button" data-days="3650">
                  10Y
                </button>
                <button type="button" data-days="0">
                  ALL
                </button>
              </div>
              <label className="chart-width-control">
                Chart width
                <input id="chartWidthRange" type="range" min="55" max="100" step="5" defaultValue="100" />
                <span id="chartWidthValue">
                  100%
                </span>
              </label>
            </div>
          </div>
          <div id="breadthCharts" className="breadth-charts adaptive-charts">
            <article className="chart-card">
              <h3>Up4% vs Down4%</h3>
              <p className="hint">Intraday tilt: more +4% names than −4% = risk-on breadth.</p>
              <div className="chart-wrap compact">
                <canvas id="upDown4Chart" />
              </div>
            </article>
            <article className="chart-card">
              <h3>5D / 10D + T2108</h3>
              <p className="hint">
                Short-term thrust: 5D/10D ratio &gt; 1 and rising T2108 = improving risk appetite.
              </p>
              <div className="chart-wrap compact">
                <canvas id="ratioChart" />
              </div>
            </article>
            <article className="chart-card">
              <h3>Up25%Q vs Down25%Q</h3>
              <p className="hint">Quarter trend health: expanding Up25%Q vs Down25%Q = trend base growing.</p>
              <div className="chart-wrap compact">
                <canvas id="quarter25Chart" />
              </div>
            </article>
            <article className="chart-card">
              <h3>Up25%M vs Down25%M</h3>
              <p className="hint">Monthly rotation: Up25%M vs Down25%M confirms near-term leadership.</p>
              <div className="chart-wrap compact">
                <canvas id="month25Chart" />
              </div>
            </article>
            <article className="chart-card">
              <h3>Up13%/34D vs Down13%/34D + S&amp;P</h3>
              <p className="hint">Index vs breadth: spot index/ breadth divergences early.</p>
              <div className="chart-wrap compact">
                <canvas id="spxBreadthChart" />
              </div>
            </article>
            <article className="chart-card">
              <h3>Up50%M vs Down50%M</h3>
              <p className="hint">Volatility pocket: spikes in Down50%M often mark risk-off phases.</p>
              <div className="chart-wrap compact">
                <canvas id="extreme50Chart" />
              </div>
            </article>
          </div>
          {!IS_READONLY ? (
          <details className="breadth-config-panel">
            <summary>Threshold Settings</summary>
            <p className="hint config-intro">
              Thresholds set OVERBOUGHT/OVERSOLD lights; anchors/tiers shade 5D/10D trend cards.
            </p>
            <div className="config-grid" id="breadthThresholdForm" />
            <div className="config-actions">
              <button id="saveBreadthConfigBtn" type="button">
                Save thresholds
              </button>
              <span id="breadthConfigStatus" className="hint" />
            </div>
          </details>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
