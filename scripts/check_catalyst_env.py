#!/usr/bin/env python3
"""Verify Finviz Elite + Gemini keys for watchlist catalyst enrichment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.catalyst_llm import probe_catalyst_pipeline


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check catalyst pipeline credentials.")
    parser.add_argument("--symbol", default="AAPL", help="Symbol for Finviz/Gemini probe")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    report = probe_catalyst_pipeline(args.symbol)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Catalyst pipeline check")
        print(f"  FINVIZ_AUTH_KEY: {'OK' if report.get('finviz_auth_key_set') else 'MISSING'}")
        print(f"  GEMINI_API_KEY:  {'OK' if report.get('gemini_api_key_set') else 'MISSING'}")
        print(f"  Finviz headlines ({report.get('test_symbol')}): {report.get('headline_count', 0)}")
        if report.get("sample_headline"):
            print(f"    sample: {report['sample_headline']}")
        if report.get("sample_tag"):
            print(f"  Gemini sample tag: {report['sample_tag']}")
        if report.get("error"):
            print(f"  issue: {report['error']}")

    if not report.get("finviz_auth_key_set") or not report.get("gemini_api_key_set"):
        return 1
    if report.get("headline_count", 0) <= 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
