#!/usr/bin/env python3
"""Write static JSON under frontend/public/data for GitHub Pages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import db_path, load_config
from src.services.public_export import export_public_dashboard


def main() -> int:
    parser = argparse.ArgumentParser(description="Export read-only dashboard JSON")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "frontend" / "public" / "data",
        help="Output directory (default: frontend/public/data)",
    )
    parser.add_argument("--db", type=Path, help="SQLite path override")
    args = parser.parse_args()

    config = load_config()
    db = args.db or db_path(config)
    meta = export_public_dashboard(args.out.resolve(), db_path=db, config=config)
    print(f"[export] wrote dashboard JSON → {args.out}")
    print(f"[export] snapshot_date={meta.get('snapshot_date')} exported_at={meta.get('exported_at')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
