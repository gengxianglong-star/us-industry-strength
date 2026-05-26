#!/usr/bin/env python3
"""对比本地 breadth_daily 与 Stockbee Market Monitor 源表。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.breadth_data import sync_breadth_history, validate_breadth_against_source
from src.config_loader import db_path, load_config
from src.storage import Storage


def main() -> int:
    parser = argparse.ArgumentParser(description="校验市场宽度与 Stockbee Sheet 一致性")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="校验前先增量同步",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="与 --sync 联用：全量重建",
    )
    args = parser.parse_args()

    config = load_config()
    storage = Storage(db_path(config))
    if args.sync:
        print("同步中…")
        sync_breadth_history(storage, full=args.full)

    result = validate_breadth_against_source(storage)
    print(
        f"源表 {result['source_row_count']} 行 · 本地 {result['local_row_count']} 行 · "
        f"不一致 {result['mismatch_count']} · 本地缺失 {result['missing_local_count']}"
    )
    if result["ok"]:
        print("校验通过：与 Stockbee 主表一致")
        return 0

    for item in result.get("mismatches") or []:
        print(
            f"  {item['trade_date']} {item['column']}: "
            f"sheet={item['source']} local={item['local']}"
        )
    if result.get("missing_local"):
        print("本地缺失日期:", ", ".join(result["missing_local"][:10]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
