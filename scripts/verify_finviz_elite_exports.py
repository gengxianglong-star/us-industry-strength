#!/usr/bin/env python3
"""Verify Finviz Elite access required for CI watchlist / industry pipeline."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from src.logging_config import setup_logging
from src.services.elite_data import elite_auth_key, elite_export_is_rate_limited, fetch_elite_market_data
from src.services.elite_groups import fetch_elite_industry_rows


def _fail_auth() -> int:
    print("[verify_elite] FAILED: FINVIZ_AUTH_KEY not set")
    print("  Get token: https://elite.finviz.com → log in → Settings → API")
    print("  Local: add FINVIZ_AUTH_KEY=... to .env")
    print("  CI:    gh secret set FINVIZ_AUTH_KEY")
    return 1


def _fail_rate_limited() -> int:
    print("[verify_elite] RATE LIMITED (HTTP 429) — Export API token is probably OK")
    print("  Finviz allows ~1 CSV export per 60 seconds.")
    print("  Wait 60–90 seconds, then retry:")
    print("    python scripts/verify_finviz_elite_exports.py")
    print("  Or wait before running:")
    print("    python scripts/verify_finviz_elite_exports.py --wait 70")
    return 2


def _fail_elite_access(exc: str) -> int:
    print("[verify_elite] FAILED: Elite industry groups unavailable")
    if elite_export_is_rate_limited(message=exc):
        return _fail_rate_limited()
    if "invalid export api token" in exc.lower():
        print("  Invalid Export API token.")
        print("  Fix: elite.finviz.com → Settings → API → Export API token")
        print("  Do NOT use auth= from a quote/screener browser URL.")
    else:
        print(f"  {exc}")
    print("  Docs: https://elite.finviz.com/api_explanation.ashx")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Finviz Elite access for CI pipeline.")
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        metavar="SEC",
        help="Sleep before the first Elite call (use 70 after HTTP 429)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also verify full-market export (extra API calls; waits 65s between steps)",
    )
    args = parser.parse_args()

    setup_logging({"logging": {"level": "INFO"}})

    key = elite_auth_key()
    if not key:
        return _fail_auth()

    if args.wait > 0:
        print(f"[verify_elite] waiting {args.wait}s (Finviz rate limit cooldown)…")
        time.sleep(args.wait)

    print("[verify_elite] checking Elite industry groups (groups.ashx v=110 + v=142)…")
    groups = fetch_elite_industry_rows(auth_key=key)
    if not groups or len(groups) < 100:
        count = 0 if not groups else len(groups)
        return _fail_elite_access(f"too few industries parsed ({count})")

    print(f"[verify_elite] industry groups OK ({len(groups)} industries)")

    if not args.full:
        print("[verify_elite] OK — Elite token valid for industry groups")
        print("  Tip: use --full to also test full-market CSV export before CI deploy")
        return 0

    print("[verify_elite] waiting 65s before full-market export (Finviz rate limit)…")
    time.sleep(65)
    print("[verify_elite] checking full-market overview export (v=111)…")
    market = fetch_elite_market_data()
    if not market:
        print("[verify_elite] FAILED: full-market Elite export unavailable")
        return 1

    with_perf = sum(1 for row in market.values() if row.get("perf_month") is not None)
    print(f"[verify_elite] market export OK ({len(market)} symbols, perf={with_perf})")
    print("[verify_elite] OK — Elite exports ready for CI watchlist pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
