#!/usr/bin/env python3
"""Export Finviz cookies from local browsers into data/finviz_cookies.txt (Netscape format)."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "finviz_cookies.txt"

BROWSER_LOADERS: tuple[str, ...] = ("edge", "arc", "chrome")


def _write_netscape(cookies, out: Path) -> None:
    lines = [
        "# Netscape HTTP Cookie File",
        "# https://curl.haxx.se/docs/http-cookies.html",
        "",
    ]
    for cookie in cookies:
        domain = cookie.domain
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if cookie.secure else "FALSE"
        expiry = str(int(cookie.expires or 0))
        lines.append(
            "\t".join(
                [
                    domain,
                    include_subdomains,
                    cookie.path,
                    secure,
                    expiry,
                    cookie.name,
                    cookie.value,
                ]
            )
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_from_browser(name: str) -> list:
    import browser_cookie3

    loader = getattr(browser_cookie3, name, None)
    if loader is None:
        raise RuntimeError(f"unsupported browser: {name}")
    cookies = [c for c in loader(domain_name="finviz.com")]
    if not cookies:
        raise RuntimeError(f"{name}: no finviz cookies found")
    if not any(c.name == "cf_clearance" for c in cookies):
        raise RuntimeError(
            f"{name}: missing cf_clearance — open https://finviz.com/screener in {name} "
            "and complete Cloudflare verification first"
        )
    return cookies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--browser",
        choices=list(BROWSER_LOADERS),
        default="",
        help="Force a specific browser profile (default: first profile with cf_clearance)",
    )
    args = parser.parse_args()

    try:
        import browser_cookie3  # noqa: F401
    except ImportError as exc:
        print("Install browser-cookie3: pip install browser-cookie3", file=sys.stderr)
        raise SystemExit(1) from exc

    candidates = BROWSER_LOADERS
    if args.browser:
        candidates = (args.browser,)

    last_error: Exception | None = None
    for name in candidates:
        try:
            cookies = export_from_browser(name)
            _write_netscape(cookies, args.out)
            print(f"Exported {len(cookies)} cookies from {name} -> {args.out}")
            return 0
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"{name}: {exc}", file=sys.stderr)

    print(f"Failed to export cookies: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
