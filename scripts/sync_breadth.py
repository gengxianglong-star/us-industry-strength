#!/usr/bin/env python3
"""增量同步 Stockbee 市场宽度（无需启动 Web 服务）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.breadth_data import sync_breadth_history
from src.config_loader import db_path, load_config
from src.storage import Storage


def main() -> int:
    parser = argparse.ArgumentParser(description="同步市场宽度 Google Sheet 数据")
    parser.add_argument(
        "--full",
        action="store_true",
        help="全量重建（慎用，会清空历史后重拉）",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config.yaml",
        help="配置文件路径",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    storage = Storage(db_path(config))
    mode = "full" if args.full else "incremental"
    print(f"市场宽度同步开始（{mode}）…")
    result = sync_breadth_history(storage, full=args.full)
    print(
        "完成："
        f"merged={result.get('merged_row_count', 0)} "
        f"kept={result.get('kept_row_count', 0)} "
        f"sheets={len(result.get('sheets', []))}"
    )
    validation = result.get("validation") or {}
    if validation.get("ok"):
        print("校验：与 Stockbee 主表一致")
    else:
        print(
            f"校验：不一致 {validation.get('mismatch_count', 0)} 处，"
            f"请运行 python scripts/validate_breadth.py"
        )
    return 0 if validation.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
