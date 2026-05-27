"""Resolve HTTP/SOCKS proxy for outbound requests (macOS system settings + env)."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from typing import Any


def detect_macos_system_proxy() -> str | None:
    """Read Web Proxy from macOS System Settings (scutil --proxy)."""
    if platform.system() != "Darwin":
        return None
    try:
        result = subprocess.run(
            ["scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return _parse_scutil_proxy_output(result.stdout or "")


def _parse_scutil_proxy_output(text: str) -> str | None:
    def _flag(name: str) -> bool:
        return bool(re.search(rf"{re.escape(name)}\s*:\s*1\b", text))

    def _field(name: str) -> str | None:
        match = re.search(rf"{re.escape(name)}\s*:\s*(\S+)", text)
        return match.group(1) if match else None

    if _flag("SOCKSEnable"):
        host = _field("SOCKSProxy")
        port = _field("SOCKSPort")
        if host and port:
            return f"socks5h://{host}:{port}"

    if _flag("HTTPSEnable"):
        host = _field("HTTPSProxy")
        port = _field("HTTPSPort")
        if host and port:
            return f"http://{host}:{port}"

    if _flag("HTTPEnable"):
        host = _field("HTTPProxy")
        port = _field("HTTPPort")
        if host and port:
            return f"http://{host}:{port}"

    return None


def proxy_from_environment() -> str | None:
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def resolve_proxy_url(
    *,
    explicit: str = "",
    use_system_proxy: bool = True,
) -> tuple[str | None, str]:
    """Return (proxy_url, source_label)."""
    if explicit.strip():
        return explicit.strip(), "config"
    if use_system_proxy:
        mac = detect_macos_system_proxy()
        if mac:
            return mac, "macos_system"
        env = proxy_from_environment()
        if env:
            return env, "environment"
    return None, "none"
