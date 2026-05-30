export function readCssVar(name: string, fallback = ""): string {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function chartThemeFromCss() {
  return {
    accent: readCssVar("--accent", "#a8b0bc"),
    text: readCssVar("--chart-text", "#8a8a96"),
    grid: readCssVar("--chart-grid", "rgba(255,255,255,0.05)"),
    ok: readCssVar("--ok", "#5a9a6e"),
    bad: readCssVar("--bad", "#9a5a5a"),
    warn: readCssVar("--warn", "#9a8a58"),
    muted: readCssVar("--accent-muted", "#787882"),
  };
}
