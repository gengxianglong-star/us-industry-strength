#!/usr/bin/env python3
"""Validate GitHub Pages export JSON under frontend/public/data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "frontend" / "public" / "data"
MIN_BYTES = 10_240
MAX_RS_BYTES = 350_000

REQUIRED_FILES = (
    "meta.json",
    "snapshot.json",
    "rs.json",
    "rs_watchlist.json",
    "automation.json",
    "breadth.json",
    "health.json",
)

SNAPSHOT_KEYS = ("snapshot_date", "industries")
RS_KEYS = ("snapshot_date", "rows", "watchlist", "rs_count")
META_KEYS = ("exported_at", "snapshot_date", "readonly")


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: root must be an object")
    return data


def validate_export_dir(out_dir: Path) -> list[str]:
    errors: list[str] = []

    for name in REQUIRED_FILES:
        path = out_dir / name
        if not path.is_file():
            errors.append(f"missing file: {path}")
            continue
        size = path.stat().st_size
        if size < MIN_BYTES and name in {"snapshot.json", "rs.json", "breadth.json"}:
            errors.append(f"{name}: size {size} < {MIN_BYTES} bytes")

    snapshot_path = out_dir / "snapshot.json"
    if snapshot_path.is_file():
        try:
            snap = _load_json(snapshot_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"snapshot.json: {exc}")
        else:
            missing = [k for k in SNAPSHOT_KEYS if k not in snap]
            if missing:
                errors.append(f"snapshot.json: missing keys {missing}")
            if not snap.get("snapshot_date"):
                errors.append("snapshot.json: snapshot_date is empty")
            industries = snap.get("industries")
            if not isinstance(industries, list) or len(industries) < 50:
                errors.append("snapshot.json: industries list too small or invalid")
            elif industries:
                sample = industries[0]
                if isinstance(sample, dict) and "trajectory_5d" not in sample:
                    errors.append("snapshot.json: industries missing trajectory_5d")

    rs_path = out_dir / "rs.json"
    if rs_path.is_file():
        try:
            rs = _load_json(rs_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"rs.json: {exc}")
        else:
            missing = [k for k in RS_KEYS if k not in rs]
            if missing:
                errors.append(f"rs.json: missing keys {missing}")
            if not rs.get("snapshot_date"):
                errors.append("rs.json: snapshot_date is empty")
            if not isinstance(rs.get("rows"), list):
                errors.append("rs.json: rows must be a list")
            if not isinstance(rs.get("watchlist"), list):
                errors.append("rs.json: watchlist must be a list")
            rs_size = rs_path.stat().st_size
            if rs_size > MAX_RS_BYTES:
                errors.append(f"rs.json: size {rs_size} > {MAX_RS_BYTES} bytes")
            rows = rs.get("rows") or []
            if rows and isinstance(rows[0], dict):
                for forbidden in ("name", "exchange"):
                    if forbidden in rows[0]:
                        errors.append(f"rs.json: rows must not include slimmed field {forbidden!r}")

    meta_path = out_dir / "meta.json"
    if meta_path.is_file():
        try:
            meta = _load_json(meta_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"meta.json: {exc}")
        else:
            missing = [k for k in META_KEYS if k not in meta]
            if missing:
                errors.append(f"meta.json: missing keys {missing}")

    return errors


def main() -> int:
    out_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT
    errors = validate_export_dir(out_dir)
    if errors:
        print("[validate_export] FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"[validate_export] OK — {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
