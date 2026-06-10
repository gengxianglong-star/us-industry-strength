#!/usr/bin/env python3
"""Smoke test for Finviz Elite full-market export engine."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.logging_config import get_logger, setup_logging
from src.services.elite_data import (
    build_elite_export_url,
    elite_auth_key,
    elite_market_filter,
    fetch_elite_market_data,
)

logger = get_logger(__name__)


def run_test() -> int:
    key = elite_auth_key()
    if not key:
        print("Elite test skipped: set FINVIZ_AUTH_KEY in your shell first.")
        print('  export FINVIZ_AUTH_KEY="your_api_token"')
        return 2

    print("Elite export URLs (for browser cross-check):")
    print(f"  overview:    {build_elite_export_url(view='111', auth_key=key)}")
    print(f"  performance: {build_elite_export_url(view='141', auth_key=key)}")
    print(f"  filter:      {elite_market_filter()}")
    print()

    data = fetch_elite_market_data()
    if not data:
        print("Elite fetch failed.")
        print("  1) Log in at https://elite.finviz.com → Settings → API → copy API token")
        print("  2) Token is NOT your login password; paste export link auth= value")
        print("  3) Open the overview URL above in browser — should download CSV, not HTML")
        print("  4) Optional: python scripts/export_finviz_cookies.py")
        return 1

    print(f"\nOK: loaded {len(data)} symbols from Elite exports.")
    print("\nSample — NVDA:")
    nvda = data.get("NVDA")
    if nvda:
        print(f"  industry:      {nvda.get('industry')}")
        print(f"  perf_month:    {nvda.get('perf_month')}")
        print(f"  rel_volume:    {nvda.get('rel_volume')}")
        print(f"  volatility_w:  {nvda.get('volatility_w')}")
    else:
        print("  NVDA not in export (unexpected)")

    with_perf = sum(1 for row in data.values() if row.get("perf_month"))
    print(f"\nSymbols with performance fields: {with_perf}/{len(data)}")
    return 0


if __name__ == "__main__":
    setup_logging({"logging": {"level": "INFO"}})
    raise SystemExit(run_test())
