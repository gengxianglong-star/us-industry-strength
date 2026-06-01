import { FormEvent, useEffect, useState } from "react";
import { fetchJson, showToast } from "../../../lib/api";

const thresholdPresets = {
  conservative: {
    tier_a_score: 0.85,
    tier_b_score: 0.72,
    core_rank_max: 20,
    max_rank_spread: 45,
    top_list_count: 8,
    acceleration_rank_delta: 8,
    pullback_midterm_rank_max: 22,
    pullback_week_rank_min: 55,
  },
  balanced: {
    tier_a_score: 0.8,
    tier_b_score: 0.66,
    core_rank_max: 25,
    max_rank_spread: 55,
    top_list_count: 10,
    acceleration_rank_delta: 6,
    pullback_midterm_rank_max: 28,
    pullback_week_rank_min: 45,
  },
  aggressive: {
    tier_a_score: 0.74,
    tier_b_score: 0.6,
    core_rank_max: 35,
    max_rank_spread: 70,
    top_list_count: 12,
    acceleration_rank_delta: 4,
    pullback_midterm_rank_max: 35,
    pullback_week_rank_min: 35,
  },
};

type ConfigShape = {
  weights: Record<string, number>;
  weights_normalized?: Record<string, number>;
  thresholds: Record<string, number>;
  stock_filters: Record<string, string>;
  stock_rs: Record<string, number | boolean>;
};

export function ConfigPanel({ onTopListChange }: { onTopListChange?: (n: number) => void }) {
  const [cfg, setCfg] = useState<ConfigShape | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetchJson<ConfigShape>("/api/config")
      .then((data) => setCfg(data))
      .catch(() => {});
  }, []);

  if (!cfg) return null;

  const w = cfg.weights || {};
  const t = cfg.thresholds || {};
  const sf = cfg.stock_filters || {};
  const rs = cfg.stock_rs || {};

  const weightHint = () => {
    const total = Object.values(w).reduce((a, b) => a + b, 0);
    const normalized = cfg.weights_normalized || {};
    const parts = Object.entries(normalized)
      .map(([k, v]) => `${k}: ${(v * 100).toFixed(1)}%`)
      .join(" · ");
    return `Weight sum ${total.toFixed(2)} · normalized → ${parts}`;
  };

  const updateWeight = (key: string, value: number) => {
    setCfg({ ...cfg, weights: { ...w, [key]: value } });
  };

  const updateThreshold = (key: string, value: number) => {
    setCfg({ ...cfg, thresholds: { ...t, [key]: value } });
    if (key === "top_list_count") onTopListChange?.(value);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setStatus("Saving…");
    try {
      const result = await fetchJson<{ config: ConfigShape }>("/api/config", {
        method: "PUT",
        body: JSON.stringify(cfg),
      });
      setCfg(result.config);
      setStatus("Saved — applies on next daily run");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Save failed");
      showToast(status, true);
    }
  };

  const applyPreset = (name: keyof typeof thresholdPresets) => {
    const preset = thresholdPresets[name];
    setCfg({ ...cfg, thresholds: { ...t, ...preset } });
    onTopListChange?.(preset.top_list_count);
    setStatus(`Applied ${name} preset — click Save to keep`);
  };

  return (
    <details className="panel config-panel" id="configPanel">
      <summary>Advanced Settings</summary>
      <div className="config-header">
        <h2>Advanced Settings</h2>
        <p className="hint">
          Saved to <code>config.yaml</code>. Let a few dailies run before tuning.
        </p>
      </div>
      <form className="config-form" onSubmit={save}>
        <fieldset>
          <legend>Cycle Weights</legend>
          <div className="config-grid weights-grid">
            {(
              [
                ["weightWeek", "week", "1W"],
                ["weightMonth", "month", "1M"],
                ["weightQuarter", "quarter", "3M"],
                ["weightHalf", "half", "6M"],
                ["weightYear", "year", "1Y"],
              ] as const
            ).map(([, key, label]) => (
              <label key={key}>
                {label}{" "}
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={w[key] ?? 0}
                  onChange={(e) => updateWeight(key, parseFloat(e.target.value))}
                />
              </label>
            ))}
          </div>
          <p className="hint">{weightHint()}</p>
        </fieldset>

        <fieldset>
          <legend>Thresholds</legend>
          <div className="config-grid">
            <label>
              Tier A score ≥ <input type="number" step="0.01" value={t.tier_a_score ?? 0.8} onChange={(e) => updateThreshold("tier_a_score", parseFloat(e.target.value))} required />
            </label>
            <label>
              Tier B score ≥ <input type="number" step="0.01" value={t.tier_b_score ?? 0.65} onChange={(e) => updateThreshold("tier_b_score", parseFloat(e.target.value))} required />
            </label>
            <label>
              Core rank cap <input type="number" value={t.core_rank_max ?? 25} onChange={(e) => updateThreshold("core_rank_max", parseInt(e.target.value, 10))} required />
            </label>
            <label>
              Max rank spread <input type="number" value={t.max_rank_spread ?? 60} onChange={(e) => updateThreshold("max_rank_spread", parseInt(e.target.value, 10))} required />
            </label>
            <label>
              Top list size <input type="number" value={t.top_list_count ?? 10} onChange={(e) => updateThreshold("top_list_count", parseInt(e.target.value, 10))} required />
            </label>
            <label>
              Accel rank gap <input type="number" value={t.acceleration_rank_delta ?? 5} onChange={(e) => updateThreshold("acceleration_rank_delta", parseInt(e.target.value, 10))} required />
            </label>
            <label>
              PB midterm rank cap <input type="number" value={t.pullback_midterm_rank_max ?? 30} onChange={(e) => updateThreshold("pullback_midterm_rank_max", parseInt(e.target.value, 10))} required />
            </label>
            <label>
              PB 1W rank floor <input type="number" value={t.pullback_week_rank_min ?? 40} onChange={(e) => updateThreshold("pullback_week_rank_min", parseInt(e.target.value, 10))} required />
            </label>
          </div>
          <div className="preset-row">
            <span className="preset-label">Presets:</span>
            <button type="button" className="preset-btn" onClick={() => applyPreset("conservative")}>
              Conservative
            </button>
            <button type="button" className="preset-btn" onClick={() => applyPreset("balanced")}>
              Balanced
            </button>
            <button type="button" className="preset-btn" onClick={() => applyPreset("aggressive")}>
              Aggressive
            </button>
          </div>
        </fieldset>

        <fieldset>
          <legend>Stock Screen (Finviz)</legend>
          <div className="config-grid">
            {Object.entries({
              stockPriceAboveSma20: "price_above_sma20",
              stockSma20AboveSma50: "sma20_above_sma50",
              stockDollarVolumeMin: "dollar_volume_min",
              stockEpsGrowthQoq: "eps_growth_qoq_min",
              stockSalesGrowthQoq: "sales_growth_qoq_min",
            }).map(([id, key]) => (
              <label key={id}>
                {key}{" "}
                <input
                  type="text"
                  value={String(sf[key] || "")}
                  onChange={(e) =>
                    setCfg({ ...cfg, stock_filters: { ...sf, [key]: e.target.value } })
                  }
                  required
                />
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend>Stock RS Parameters</legend>
          <div className="config-grid">
            <label>
              Timeout (sec)
              <input type="number" value={Number(rs.request_timeout_seconds ?? 20)} onChange={(e) => setCfg({ ...cfg, stock_rs: { ...rs, request_timeout_seconds: parseInt(e.target.value, 10) } })} required />
            </label>
            <label>
              Min price bars
              <input type="number" value={Number(rs.min_price_rows ?? 260)} onChange={(e) => setCfg({ ...cfg, stock_rs: { ...rs, min_price_rows: parseInt(e.target.value, 10) } })} required />
            </label>
            <label>
              RS Tier A ≥
              <input type="number" step="0.01" value={Number(rs.tier_a_score ?? 0.8)} onChange={(e) => setCfg({ ...cfg, stock_rs: { ...rs, tier_a_score: parseFloat(e.target.value) } })} required />
            </label>
            <label>
              RS Tier B ≥
              <input type="number" step="0.01" value={Number(rs.tier_b_score ?? 0.65)} onChange={(e) => setCfg({ ...cfg, stock_rs: { ...rs, tier_b_score: parseFloat(e.target.value) } })} required />
            </label>
            <label>
              Cross top %
              <input type="number" step="0.01" value={Number(rs.cross_top_percent ?? 0.1)} onChange={(e) => setCfg({ ...cfg, stock_rs: { ...rs, cross_top_percent: parseFloat(e.target.value) } })} required />
            </label>
            <label>
              Universe cap (0 = all)
              <input type="number" value={Number(rs.universe_cap ?? 0)} onChange={(e) => setCfg({ ...cfg, stock_rs: { ...rs, universe_cap: parseInt(e.target.value, 10) } })} required />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={Boolean(rs.prefer_stooq)}
                onChange={(e) => setCfg({ ...cfg, stock_rs: { ...rs, prefer_stooq: e.target.checked } })}
              />
              Prefer Stooq (fallback Yahoo)
            </label>
          </div>
        </fieldset>

        <div className="config-actions">
          <button type="submit">Save settings</button>
          <p className="hint">Server auto-runs daily jobs; changes apply on the next run.</p>
          <span className={`config-status${status.includes("fail") ? " error" : ""}`} aria-live="polite">
            {status}
          </span>
        </div>
      </form>
    </details>
  );
}
