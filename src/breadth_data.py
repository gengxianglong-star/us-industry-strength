"""Sync and analyze Stockbee market breadth history."""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from src.config_loader import load_config
from src.logging_config import get_logger
from src.proxy_util import resolve_proxy_url
from src.storage import Storage

logger = get_logger(__name__)

SHEET_ID = "1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE"
SHEET_PUBHTML_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/pubhtml"
SHEET_CSV_GID_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={{gid}}"
# Market Monitor 主表（与用户提供的 Stockbee 链接 gid 一致）
PRIMARY_MARKET_MONITOR_GID = "1082103394"
# 增量同步时回刷最近 N 天，覆盖 Sheet 对已发布日期的修订（如 118→119）
INCREMENTAL_LOOKBACK_DAYS = 120

DEFAULT_THRESHOLDS: dict[str, float] = {
    "trend10_overbought_min": 2.0,
    "trend10_oversold_max": 0.5,
    "trend5_overbought_min": 2.0,
    "trend5_oversold_max": 0.5,
    "t2108_red_max": 20.0,
    "t2108_green_min": 60.0,
    "ratio_green_anchor": 1.5,
    "ratio_green_low_min": 1.0,
    "ratio_green_high_max": 2.0,
    "ratio_green_tier_count": 5.0,
    "ratio_red_anchor": 0.75,
    "ratio_red_low_min": 0.5,
    "ratio_red_high_max": 1.0,
    "ratio_red_tier_count": 5.0,
}


def validate_breadth_thresholds(cfg: dict[str, float]) -> None:
    """校验阈值组合，非法时抛出 ValueError。"""
    merged = dict(DEFAULT_THRESHOLDS)
    merged.update(cfg)

    def _check_range(low_key: str, anchor_key: str, high_key: str, label: str) -> None:
        low = float(merged[low_key])
        anchor = float(merged[anchor_key])
        high = float(merged[high_key])
        if not low < anchor < high:
            raise ValueError(f"{label}：下限 < 锚点 < 上限")

    def _check_tiers(key: str, label: str) -> None:
        tiers = int(float(merged[key]))
        if tiers < 2 or tiers > 10:
            raise ValueError(f"{label}：档数须在 2–10 之间")

    _check_range("ratio_green_low_min", "ratio_green_anchor", "ratio_green_high_max", "5/10日绿背景")
    _check_range("ratio_red_low_min", "ratio_red_anchor", "ratio_red_high_max", "5/10日红背景")
    _check_tiers("ratio_green_tier_count", "绿侧档数")
    _check_tiers("ratio_red_tier_count", "红侧档数")

    if float(merged["trend10_oversold_max"]) >= float(merged["trend10_overbought_min"]):
        raise ValueError("10D：Oversold 上限须小于 Overbought 下限")
    if float(merged["trend5_oversold_max"]) >= float(merged["trend5_overbought_min"]):
        raise ValueError("5D：Oversold 上限须小于 Overbought 下限")
    if float(merged["t2108_red_max"]) >= float(merged["t2108_green_min"]):
        raise ValueError("T2108：Red 上限须小于 Green 下限")


def resolve_ratio_bg_params(thresholds: dict[str, float]) -> dict[str, dict[str, float | int]]:
    """解析 5/10 日趋势背景分档参数（供前端与说明文案共用）。"""
    green_tiers = max(2, min(10, int(float(thresholds.get("ratio_green_tier_count", 5)))))
    red_tiers = max(2, min(10, int(float(thresholds.get("ratio_red_tier_count", 5)))))
    green_anchor = float(thresholds["ratio_green_anchor"])
    green_low = float(thresholds["ratio_green_low_min"])
    green_high = float(thresholds["ratio_green_high_max"])
    red_anchor = float(thresholds["ratio_red_anchor"])
    red_low = float(thresholds["ratio_red_low_min"])
    red_high = float(thresholds["ratio_red_high_max"])
    return {
        "green": {
            "anchor": green_anchor,
            "low_min": green_low,
            "high_max": green_high,
            "tier_count": green_tiers,
            "tier_max": green_tiers - 1,
            "band_below": (green_anchor - green_low) / green_tiers,
            "band_above": (green_high - green_anchor) / green_tiers,
        },
        "red": {
            "anchor": red_anchor,
            "low_min": red_low,
            "high_max": red_high,
            "tier_count": red_tiers,
            "tier_max": red_tiers - 1,
            "band_below": (red_anchor - red_low) / red_tiers,
            "band_above": (red_high - red_anchor) / red_tiers,
        },
    }


def build_cockpit_help(thresholds: dict[str, float]) -> list[dict[str, Any]]:
    """驾驶舱模块触发条件与背景分档说明。"""
    t10_ob = float(thresholds["trend10_overbought_min"])
    t10_os = float(thresholds["trend10_oversold_max"])
    t5_ob = float(thresholds["trend5_overbought_min"])
    t5_os = float(thresholds["trend5_oversold_max"])
    t_red = float(thresholds["t2108_red_max"])
    t_green = float(thresholds["t2108_green_min"])
    ratio = resolve_ratio_bg_params(thresholds)
    g = ratio["green"]
    r = ratio["red"]

    def _fmt(v: float) -> str:
        return f"{v:g}"

    trend_bg_lines = [
        f"Green anchor {_fmt(g['anchor'])} (same as quarter/half/month/5-10 green lights)",
        f"Range [{_fmt(g['low_min'])}, {_fmt(g['high_max'])}], {int(g['tier_count'])} tiers below/above anchor (step ~{_fmt(g['band_below'])} / {_fmt(g['band_above'])})",
        "Ratio below anchor = lighter; above = deeper; out of range = min/max shade",
        f"Red anchor {_fmt(r['anchor'])} (same as the four red-light modules)",
        f"Range [{_fmt(r['low_min'])}, {_fmt(r['high_max'])}], {int(r['tier_count'])} tiers below/above anchor (step ~{_fmt(r['band_below'])} / {_fmt(r['band_above'])})",
        "Ratio below anchor = deeper; above = lighter",
    ]
    trend_state_lines = [
        "≥ overbought floor → OVERBOUGHT (green)",
        "≤ oversold cap → OVERSOLD (red)",
        "Between and ≥ 1 → NORMAL (green, stronger as ratio rises)",
        "< 1 and not oversold → NORMAL (red, weaker as ratio falls)",
    ]

    return [
        {
            "id": "quarter_trend",
            "title": "Quarter Trend",
            "lines": [
                "Up25%Q > Down25%Q → green BULL",
                "else → red BEAR",
                "Background matches full-strength light color",
            ],
        },
        {
            "id": "half_season_trend",
            "title": "Half Quarter Trend",
            "lines": [
                "Up13%/34D > Down13%/34D → green BULL",
                "else → red BEAR",
                "Background matches full-strength light color",
            ],
        },
        {
            "id": "monthly_trend",
            "title": "Monthly Trend",
            "lines": [
                "Up25%M > Down25%M → green BULLISH",
                "else → red BEARISH",
                "Background matches full-strength light color",
            ],
        },
        {
            "id": "cross_5_10",
            "title": "5-10 Cross",
            "lines": [
                "5D ratio ≥ 10D ratio → green LONG",
                "else → red SHORT",
                "Background matches full-strength light color",
            ],
        },
        {
            "id": "trend_10d",
            "title": "10D Trend",
            "lines": [
                f"10D Overbought ≥ {_fmt(t10_ob)}；Oversold ≤ {_fmt(t10_os)}",
                *trend_state_lines,
                *trend_bg_lines,
            ],
        },
        {
            "id": "trend_5d",
            "title": "5D Trend",
            "lines": [
                f"5D Overbought ≥ {_fmt(t5_ob)}；Oversold ≤ {_fmt(t5_os)}",
                *trend_state_lines,
                *trend_bg_lines,
            ],
        },
        {
            "id": "extreme_alert",
            "title": "T2108 Alert",
            "lines": [
                f"≤ {_fmt(t_red)} → OVERSOLD (red, deeper = lower)",
                f"≥ {_fmt(t_green)} → OVERBOUGHT (green, deeper = higher)",
                "Between → NORMAL (neutral)",
            ],
        },
    ]

_CACHE_TTL_SECONDS = 300
_CACHE_DATA: dict[str, Any] | None = None
_CACHE_AT: float = 0.0
_CACHE_SIGNATURE: str = ""
_CACHE_LIMIT: int = 0
_CACHE_LOCK = threading.Lock()


def _to_number(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    return text


def _is_iso_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        return False
    try:
        dt = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return False
    year = dt.year
    return 2007 <= year <= (datetime.utcnow().year + 1)


def _discover_gids_from_pubhtml(settings: dict[str, Any]) -> list[str]:
    """List sheet tab gids from the published workbook HTML."""
    cmd = [
        _curl_binary(),
        "-fsSL",
        "--http1.1",
        "--max-time",
        str(int(settings.get("read_timeout_seconds", 120))),
        "-A",
        settings["user_agent"],
    ]
    proxy = str(settings.get("proxy_url") or "").strip()
    if proxy:
        cmd.extend(["--proxy", proxy])
    if not settings.get("verify_ssl", True):
        cmd.append("--insecure")
    cmd.append(SHEET_PUBHTML_URL)
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"curl exit {result.returncode}")
    text = result.stdout.decode("utf-8", errors="replace")
    return sorted(set(re.findall(r"gid=(\d+)", text)), key=int)


def _gid_has_breadth_data(gid: str, settings: dict[str, Any]) -> bool:
    """True when a tab exports at least ~1 month of valid Market Monitor rows."""
    try:
        _, _, data_rows = _fetch_gid_rows_remote(gid, settings)
        rows = _normalize_gid_rows(gid, f"gid_{gid}", data_rows)
        return len(rows) >= 20
    except Exception:
        logger.debug("breadth tab validation failed (ignored)", exc_info=True)
        return False


def _discover_sheet_gids(
    config: dict[str, Any] | None = None,
    *,
    full: bool = False,
    storage: Storage | None = None,
) -> list[str]:
    """Return sheet gids to sync.

    Stockbee history is split across many yearly tabs. Full sync discovers all tabs
    from pubhtml; incremental sync only hits the live tab plus sheets touched recently.
    """
    cfg = config or load_config()
    settings = _breadth_settings(cfg)
    primary = PRIMARY_MARKET_MONITOR_GID

    if not full and storage is not None:
        lookback_cutoff = (
            datetime.now(timezone.utc).date() - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)
        ).isoformat()
        gids: list[str] = [primary]
        for item in storage.get_breadth_sheet_meta():
            gid = str(item.get("sheet_gid") or "").strip()
            if not gid or gid == primary:
                continue
            last_date = str(item.get("last_date") or "")
            if last_date and last_date >= lookback_cutoff:
                gids.append(gid)
        return list(dict.fromkeys(gids))

    try:
        candidates = _discover_gids_from_pubhtml(settings)
    except Exception:
        logger.debug("breadth gid discovery failed, using primary only", exc_info=True)
        candidates = [primary]

    valid: list[str] = []
    for gid in candidates:
        if gid == primary or _gid_has_breadth_data(gid, settings):
            if gid not in valid:
                valid.append(gid)

    if primary not in valid:
        valid.insert(0, primary)
    else:
        valid = [primary] + [g for g in valid if g != primary]
    return valid


def _breadth_settings(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict((config or load_config()).get("breadth") or {})
    scraper = dict((config or load_config()).get("scraper") or {})
    read_timeout = int(cfg.get("read_timeout_seconds", cfg.get("request_timeout_seconds", 120)))
    explicit_proxy = str(cfg.get("proxy_url") or "").strip()
    use_system_proxy = bool(cfg.get("use_system_proxy", True))
    resolved_proxy, proxy_source = resolve_proxy_url(
        explicit=explicit_proxy,
        use_system_proxy=use_system_proxy,
    )
    cookie_file = str(cfg.get("cookie_file") or scraper.get("cookie_file") or "").strip()
    prefer_curl = cfg.get("prefer_curl")
    if prefer_curl is None:
        prefer_curl = True
    curl_only = cfg.get("curl_only")
    if curl_only is None:
        curl_only = True
    return {
        "connect_timeout_seconds": int(cfg.get("connect_timeout_seconds", 20)),
        "read_timeout_seconds": read_timeout,
        "request_timeout_seconds": read_timeout,
        "request_retries": int(cfg.get("request_retries", 5)),
        "proxy_url": resolved_proxy or "",
        "proxy_source": proxy_source,
        "explicit_proxy_url": explicit_proxy,
        "use_system_proxy": use_system_proxy,
        "verify_ssl": bool(cfg.get("verify_ssl", True)),
        "prefer_curl": bool(prefer_curl),
        "curl_only": bool(curl_only),
        "validate_after_sync": bool(cfg.get("validate_after_sync", False)),
        "cookie_file": cookie_file,
        "local_csv_path": str(cfg.get("local_csv_path") or "").strip(),
        "offline_only": bool(cfg.get("offline_only", False)),
        "user_agent": str(
            cfg.get("user_agent")
            or scraper.get("user_agent")
            or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }


def _breadth_http_session(settings: dict[str, Any]) -> requests.Session:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    session.trust_env = bool(settings.get("use_system_proxy", True))
    proxy_url = str(settings.get("proxy_url") or "").strip()
    if proxy_url:
        session.proxies.update({"http": proxy_url, "https": proxy_url})
    verify_ssl = bool(settings.get("verify_ssl", True))
    session.verify = verify_ssl
    retry = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=0,
        status=0,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": settings["user_agent"],
            "Accept": "text/csv,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "close",
        }
    )
    return session


def _is_google_sheet_fetch_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "docs.google.com",
            "googleusercontent.com",
            "ssl",
            "ssleoferror",
            "unexpected_eof",
            "connection",
            "timeout",
        )
    )


def _format_breadth_fetch_error(exc: Exception, settings: dict[str, Any]) -> str:
    message = str(exc)
    if not _is_google_sheet_fetch_error(message):
        return message
    hints = [
        "浏览器能打开 Google Sheet，但 Python 同步默认不会自动走「系统设置」里的代理。",
        "本程序已尝试：读取 macOS 系统代理 + 使用 curl 下载（与浏览器更接近）。",
        "若仍失败，请任选：",
        "1) 在 config.yaml 填写 breadth.proxy_url（与浏览器代理端口一致，如 http://127.0.0.1:7890）；",
        "2) 改用 SOCKS5：socks5h://127.0.0.1:7891；",
        "3) breadth.verify_ssl: false（仅当代理做 HTTPS 解密时）；",
        "4) 浏览器导出 CSV → breadth.local_csv_path + offline_only: true。",
    ]
    proxy = settings.get("proxy_url") or ""
    source = settings.get("proxy_source") or "none"
    if proxy:
        hints.append(f"当前使用代理：{proxy}（来源 {source}）")
    else:
        hints.append("当前未检测到可用代理（proxy_source=none）")
    if settings.get("prefer_curl"):
        hints.append("prefer_curl=true（优先 curl）")
    return "\n".join(hints) + f"\n原始错误：{message}"


def _parse_csv_export(text: str) -> tuple[list[str], list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        return [], [], []
    group_row = [x.strip() for x in rows[0]]
    header_row = [x.strip() for x in rows[1]]
    data_rows = rows[2:]
    return group_row, header_row, data_rows


def _read_local_csv_export(path: Path) -> tuple[list[str], list[str], list[list[str]]]:
    text = path.read_text(encoding="utf-8-sig")
    parsed = _parse_csv_export(text)
    if not parsed[2]:
        raise ValueError(f"本地 CSV 无有效数据行：{path}")
    return parsed


def _curl_binary() -> str:
    for candidate in ("/usr/bin/curl", shutil.which("curl")):
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("未找到 curl（需要 macOS 自带 /usr/bin/curl）")


def _download_csv_via_curl(url: str, settings: dict[str, Any], *, proxy: str | None = None) -> str:
    read_timeout = int(settings["read_timeout_seconds"])
    cmd = [
        _curl_binary(),
        "-fsSL",
        "--http1.1",
        "--max-time",
        str(read_timeout),
        "-A",
        settings["user_agent"],
        "-H",
        "Accept: text/csv,text/plain,*/*",
    ]
    proxy = proxy if proxy is not None else str(settings.get("proxy_url") or "").strip() or None
    if proxy:
        cmd.extend(["--proxy", proxy])
    if not settings.get("verify_ssl", True):
        cmd.append("--insecure")
    cookie_file = str(settings.get("cookie_file") or "").strip()
    if cookie_file and Path(cookie_file).is_file():
        cmd.extend(["-b", cookie_file])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        hint = f" [proxy={proxy or 'none'}]" if proxy else " [proxy=none]"
        raise RuntimeError((stderr or f"curl exit {result.returncode}") + hint)
    payload = result.stdout
    if not payload.strip():
        raise ValueError("curl 返回空内容")
    return payload.decode("utf-8-sig", errors="replace")


def _download_csv_via_curl_with_fallbacks(url: str, settings: dict[str, Any]) -> str:
    from src.proxy_util import detect_macos_system_proxy

    proxies: list[str | None] = []
    primary = str(settings.get("proxy_url") or "").strip()
    if primary:
        proxies.append(primary)
    mac = detect_macos_system_proxy()
    if mac and mac not in proxies:
        proxies.append(mac)
    explicit = str(settings.get("explicit_proxy_url") or "").strip()
    if explicit and explicit not in proxies:
        proxies.append(explicit)

    errors: list[str] = []
    for proxy in proxies or [None]:
        try:
            return _download_csv_via_curl(url, settings, proxy=proxy)
        except (RuntimeError, ValueError, OSError) as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors[-3:]))


def _download_csv_text(session: requests.Session, url: str, settings: dict[str, Any]) -> str:
    connect_timeout = int(settings["connect_timeout_seconds"])
    read_timeout = int(settings["read_timeout_seconds"])
    timeout = (connect_timeout, read_timeout)
    verify_ssl = bool(settings.get("verify_ssl", True))
    with session.get(url, timeout=timeout, verify=verify_ssl, stream=True, allow_redirects=True) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if chunk:
                chunks.append(chunk)
    payload = b"".join(chunks)
    if not payload.strip():
        raise ValueError("Google Sheet 返回空内容")
    return payload.decode("utf-8-sig", errors="replace")


def _fetch_gid_rows_remote(gid: str, settings: dict[str, Any]) -> tuple[list[str], list[str], list[list[str]]]:
    urls = [
        SHEET_CSV_GID_URL.format(gid=gid),
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={gid}",
    ]
    retries = max(1, int(settings["request_retries"]))
    curl_only = bool(settings.get("curl_only", True))
    try:
        _curl_binary()
        use_curl = bool(settings.get("prefer_curl", True))
    except RuntimeError:
        use_curl = False
    last_exc: Exception | None = None

    for url_idx, url in enumerate(urls):
        for attempt in range(retries):
            try:
                if use_curl:
                    text = _download_csv_via_curl_with_fallbacks(url, settings)
                else:
                    session = _breadth_http_session(settings)
                    text = _download_csv_text(session, url, settings)
                parsed = _parse_csv_export(text)
                if not parsed[2]:
                    raise ValueError("CSV 解析后无数据行")
                return parsed
            except Exception as exc:
                logger.warning(
                    "breadth fetch attempt %d/%d failed: %s",
                    attempt + 1, retries, exc,
                )
                last_exc = exc
                if not curl_only and use_curl:
                    try:
                        session = _breadth_http_session(settings)
                        text = _download_csv_text(session, url, settings)
                        parsed = _parse_csv_export(text)
                        if parsed[2]:
                            return parsed
                    except Exception as req_exc:
                        logger.debug("breadth HTTP fallback also failed: %s", req_exc)
                        last_exc = req_exc
                if attempt + 1 < retries:
                    time.sleep(min(2**attempt, 10))
                    continue
                if url_idx + 1 < len(urls):
                    break
    raise RuntimeError(_format_breadth_fetch_error(last_exc or RuntimeError("fetch failed"), settings)) from last_exc


def _fetch_gid_rows(
    gid: str,
    config: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[list[str]]]:
    settings = _breadth_settings(config)
    local_path = (
        Path(settings["local_csv_path"]).expanduser()
        if settings.get("local_csv_path")
        else None
    )
    offline_only = bool(settings.get("offline_only", False))

    if not offline_only:
        try:
            return _fetch_gid_rows_remote(gid, settings)
        except Exception as exc:
            logger.warning("breadth remote fetch failed, trying local fallback: %s", exc)
            if local_path and local_path.is_file():
                return _read_local_csv_export(local_path)
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(_format_breadth_fetch_error(exc, settings)) from exc

    if local_path and local_path.is_file():
        return _read_local_csv_export(local_path)
    raise RuntimeError(
        "breadth.offline_only=true 但未配置可用的 breadth.local_csv_path"
    )


def _normalize_gid_rows(gid: str, sheet_name: str, rows: list[list[str]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not row or not row[0].strip():
            continue
        trade_date = _parse_date(row[0].strip())
        if not _is_iso_date(trade_date):
            continue
        raw_values = {}
        item: dict[str, Any] = {
            "trade_date": trade_date,
            "raw_date": row[0].strip(),
            "sheet_gid": gid,
            "sheet_name": sheet_name,
            "raw_values": raw_values,
        }
        for idx in range(1, 16):
            text_val = row[idx].strip() if idx < len(row) else ""
            raw_values[f"c{idx}"] = text_val
            item[f"c{idx}"] = _to_number(text_val)
        normalized.append(item)
    return normalized


def sync_breadth_history(
    storage: Storage,
    *,
    full: bool = False,
    progress_callback: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global _CACHE_DATA, _CACHE_AT, _CACHE_SIGNATURE, _CACHE_LIMIT
    cfg = config or load_config()
    gids = _discover_sheet_gids(cfg, full=full, storage=storage)
    if progress_callback:
        progress_callback(0, len(gids), "discover")
    existing_meta = storage.get_breadth_sheet_meta()
    last_date_by_gid = {
        str(item.get("sheet_gid")): str(item.get("last_date") or "")
        for item in existing_meta
    }
    if full:
        storage.clear_breadth_history()
    all_rows: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    kept_rows = 0
    for i, gid in enumerate(gids, start=1):
        group_row, header_row, data_rows = _fetch_gid_rows(gid, cfg)
        sheet_name = f"gid_{gid}"
        rows = _normalize_gid_rows(gid, sheet_name, data_rows)
        if not rows:
            if progress_callback:
                progress_callback(i, len(gids), gid)
            continue
        source_dates = sorted([r["trade_date"] for r in rows])
        if full:
            rows_to_save = rows
        else:
            lookback_cutoff = (
                datetime.now(timezone.utc).date() - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)
            ).isoformat()
            last_date = last_date_by_gid.get(gid, "")
            # 增量：新日期 + 最近窗口内全部重拉（Stockbee 会修订已发布单元格）
            min_date = lookback_cutoff
            if last_date and last_date < min_date:
                min_date = last_date
            rows_to_save = [r for r in rows if r["trade_date"] >= min_date]
        all_rows.extend(rows_to_save)
        kept_rows += len(rows_to_save)
        dates = sorted([r["trade_date"] for r in rows])
        metas.append(
            {
                "sheet_gid": gid,
                "sheet_name": sheet_name,
                "first_date": source_dates[0] if source_dates else None,
                "last_date": source_dates[-1] if source_dates else None,
                "row_count": len(rows),
                "group_headers": group_row,
                "headers": header_row,
            }
        )
        if progress_callback:
            progress_callback(i, len(gids), gid)

    storage.save_breadth_raw_rows(all_rows)
    storage.upsert_breadth_sheet_meta(metas)
    merged_count = storage.rebuild_breadth_daily_from_raw()
    _CACHE_DATA = None
    _CACHE_AT = 0.0
    _CACHE_SIGNATURE = ""
    _CACHE_LIMIT = 0
    validation: dict[str, Any] = {"ok": True, "skipped": True}
    if cfg.get("validate_after_sync", False):
        try:
            validation = validate_breadth_against_source(storage, config=cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("breadth validation failed: %s", exc)
            validation = {"ok": False, "skipped": False, "warning": str(exc)}
    return {
        "mode": "full" if full else "incremental",
        "sheet_count": len(gids),
        "raw_row_count": len(all_rows),
        "kept_row_count": kept_rows,
        "merged_row_count": merged_count,
        "sheets": metas,
        "validation": validation,
    }


def fetch_source_breadth_rows(
    gid: str = PRIMARY_MARKET_MONITOR_GID,
    *,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """从 Google Sheet 拉取并规范化 Market Monitor 行（用于校验）。"""
    _, _, data_rows = _fetch_gid_rows(gid, config)
    return _normalize_gid_rows(gid, f"gid_{gid}", data_rows)


def validate_breadth_against_source(
    storage: Storage,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """逐日逐列对比本地 breadth_daily 与 Sheet 源数据。"""
    source_rows = {r["trade_date"]: r for r in fetch_source_breadth_rows(config=config)}
    local_rows = {r["trade_date"]: r for r in storage.get_breadth_daily(limit=10000)}
    mismatches: list[dict[str, Any]] = []
    missing_local: list[str] = []
    missing_source: list[str] = []

    for trade_date, src in sorted(source_rows.items()):
        loc = local_rows.get(trade_date)
        if not loc:
            missing_local.append(trade_date)
            continue
        for col in [f"c{i}" for i in range(1, 16)]:
            sv = _to_number(src.get(col))
            lv = _to_number(loc.get(col))
            if sv is None and lv is None:
                continue
            if sv is None or lv is None or abs(sv - lv) > 1e-6:
                mismatches.append(
                    {
                        "trade_date": trade_date,
                        "column": col,
                        "source": sv,
                        "local": lv,
                    }
                )

    for trade_date in sorted(local_rows.keys()):
        if trade_date not in source_rows:
            missing_source.append(trade_date)

    return {
        "source_row_count": len(source_rows),
        "local_row_count": len(local_rows),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:50],
        "missing_local_count": len(missing_local),
        "missing_local": missing_local[:20],
        "missing_source_count": len(missing_source),
        "missing_source": missing_source[:20],
        "ok": (
            not mismatches
            and not missing_local
            and len(local_rows) == len(source_rows)
        ),
    }


def _pct_rank(values: list[float], x: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    pos = sum(1 for v in sorted_vals if v <= x)
    return round((pos / n) * 100, 2)


def _ratio_trend_state(value: float, overbought_min: float, oversold_max: float) -> tuple[str, str, float]:
    if value >= overbought_min:
        intensity = min(1.0, max(0.0, (value - overbought_min) / max(0.8, overbought_min)))
        return "OVERBOUGHT", "green", intensity
    if value <= oversold_max:
        intensity = min(1.0, max(0.0, (oversold_max - value) / max(0.1, oversold_max)))
        return "OVERSOLD", "red", intensity
    if value >= 1.0:
        intensity = min(1.0, max(0.0, (value - 1.0) / max(0.1, overbought_min - 1.0)))
        return "NORMAL", "green", intensity
    intensity = min(1.0, max(0.0, (1.0 - value) / max(0.1, 1.0 - oversold_max)))
    return "NORMAL", "red", intensity


def _build_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    latest = rows[0]
    cards = [
        ("up4", "Up 4% Daily", "c1"),
        ("down4", "Down 4% Daily", "c2"),
        ("ratio10", "10 Day Ratio", "c4"),
        ("up25q", "Up 25% Quarter", "c5"),
        ("down25q", "Down 25% Quarter", "c6"),
        ("t2108", "T2108", "c14"),
    ]
    result = []
    for key, label, col in cards:
        values = [_to_number(r.get(col)) for r in rows]
        series = [v for v in values if v is not None]
        current = _to_number(latest.get(col))
        if current is None:
            continue
        result.append(
            {
                "key": key,
                "label": label,
                "value": round(current, 3),
                "history_percentile": _pct_rank(series, current),
            }
        )
    return result


def load_breadth_data(
    storage: Storage,
    force_refresh: bool = False,
    limit: int = 180,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global _CACHE_DATA, _CACHE_AT, _CACHE_SIGNATURE, _CACHE_LIMIT, _CACHE_LIMIT
    cfg = config or load_config()
    now = time.time()
    fetch_limit = min(max(limit, 10), 12000)
    current_signature = storage.get_breadth_cache_signature()
    with _CACHE_LOCK:
        if (
            not force_refresh
            and _CACHE_DATA
            and _CACHE_SIGNATURE == current_signature
            and _CACHE_LIMIT >= fetch_limit
            and (now - _CACHE_AT) < _CACHE_TTL_SECONDS
        ):
            payload = dict(_CACHE_DATA)
            payload["rows"] = payload["rows"][:limit]
            payload["limit"] = limit
            return payload

    rows = storage.get_breadth_daily(limit=fetch_limit)
    if not rows:
        raise ValueError("Breadth data is empty — run sync first")

    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(storage.get_breadth_threshold_overrides())

    latest = rows[0]
    up_q = _to_number(latest.get("c5")) or 0.0
    down_q = _to_number(latest.get("c6")) or 0.0
    up_h = _to_number(latest.get("c11")) or 0.0
    down_h = _to_number(latest.get("c12")) or 0.0
    up_m = _to_number(latest.get("c7")) or 0.0
    down_m = _to_number(latest.get("c8")) or 0.0
    ratio10 = _to_number(latest.get("c4")) or 0.0
    ratio5 = _to_number(latest.get("c3")) or 0.0
    t2108 = _to_number(latest.get("c14")) or 0.0

    quarter_state = "BULL" if up_q > down_q else "BEAR"
    quarter_color = "green" if up_q > down_q else "red"
    half_state = "BULL" if up_h > down_h else "BEAR"
    half_color = "green" if up_h > down_h else "red"
    month_state = "BULLISH" if up_m > down_m else "BEARISH"
    month_color = "green" if up_m > down_m else "red"
    cross_state = "LONG" if ratio5 >= ratio10 else "SHORT"
    cross_color = "green" if ratio5 >= ratio10 else "red"

    r10_state, r10_color, r10_intensity = _ratio_trend_state(
        ratio10,
        float(thresholds["trend10_overbought_min"]),
        float(thresholds["trend10_oversold_max"]),
    )
    r5_state, r5_color, r5_intensity = _ratio_trend_state(
        ratio5,
        float(thresholds["trend5_overbought_min"]),
        float(thresholds["trend5_oversold_max"]),
    )

    t_red = float(thresholds["t2108_red_max"])
    t_green = float(thresholds["t2108_green_min"])
    if t2108 <= t_red:
        t_state = "OVERSOLD"
        t_color = "red"
        t_intensity = min(1.0, max(0.0, (t_red - t2108) / max(1.0, t_red)))
    elif t2108 >= t_green:
        t_state = "OVERBOUGHT"
        t_color = "green"
        t_intensity = min(1.0, max(0.0, (t2108 - t_green) / max(1.0, 100 - t_green)))
    else:
        t_state = "NORMAL"
        t_color = "white"
        t_intensity = 0.0

    coverage = storage.get_breadth_coverage()
    sheet_meta = storage.get_breadth_sheet_meta()

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        rv = row.get("raw_values") or {}
        out = {
            "date": row.get("trade_date"),
            "raw_date": row.get("raw_date") or row.get("trade_date"),
        }
        for idx in range(1, 16):
            key = f"c{idx}"
            out[key] = str(rv.get(key) or "")
            out[f"{key}_num"] = row.get(key)
        normalized_rows.append(out)

    payload = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "group_headers": [
            "",
            "Primary Breadth Indicators",
            "",
            "",
            "",
            "",
            "",
            "Secondary Breadth Indicators",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        "headers": [
            "Date",
            "Number of stocks up 4% plus today",
            "Number of stocks down 4% plus today",
            "5 day ratio",
            "10 day ratio",
            "Number of stocks up 25% plus in a quarter",
            "Number of stocks down 25% + in a quarter",
            "Number of stocks up 25% + in a month",
            "Number of stocks down 25% + in a month",
            "Number of stocks up 50% + in a month",
            "Number of stocks down 50% + in a month",
            "Number of stocks up 13% + in 34 days",
            "Number of stocks down 13% + in 34 days",
            "Worden Common stock universe",
            "T2108",
            "S&P",
        ],
        "rows": normalized_rows,
        "row_count": len(normalized_rows),
        "source": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        "coverage": coverage,
        "sheet_meta": sheet_meta,
        "thresholds": thresholds,
        "ratio_bg": resolve_ratio_bg_params(thresholds),
        "cockpit_help": build_cockpit_help(thresholds),
        "status": {
            "quarter_trend": {
                "title": "Quarter",
                "state": quarter_state,
                "color": quarter_color,
                "intensity": 1.0,
                "value": f"Up25Q {up_q:.0f} / Down25Q {down_q:.0f}",
            },
            "half_season_trend": {
                "title": "Half Quarter",
                "state": half_state,
                "color": half_color,
                "intensity": 1.0,
                "value": f"Up13/34D {up_h:.0f} / Down13/34D {down_h:.0f}",
            },
            "monthly_trend": {
                "title": "Monthly",
                "state": month_state,
                "color": month_color,
                "intensity": 1.0,
                "value": f"Up25M {up_m:.0f} / Down25M {down_m:.0f}",
            },
            "cross_5_10": {
                "title": "5-10 Cross",
                "state": cross_state,
                "color": cross_color,
                "intensity": 1.0,
                "value": f"5D {ratio5:.2f} / 10D {ratio10:.2f}",
            },
            "trend_10d": {
                "title": "10D Trend",
                "state": r10_state,
                "color": r10_color,
                "intensity": round(r10_intensity, 3),
                "value": round(ratio10, 3),
            },
            "trend_5d": {
                "title": "5D Trend",
                "state": r5_state,
                "color": r5_color,
                "intensity": round(r5_intensity, 3),
                "value": round(ratio5, 3),
            },
            "extreme_alert": {
                "title": "T2108",
                "state": t_state,
                "color": t_color,
                "intensity": round(t_intensity, 3),
                "value": round(t2108, 2),
            },
        },
        "percentile_cards": _build_cards(normalized_rows),
        "notes": {
            "indicators_explain_url": "https://stockbee.blogspot.com/2022/12/market-monitor-scans.html",
            "overview_url": "https://stockbee.blogspot.com/p/mm.html",
        },
    }
    with _CACHE_LOCK:
        _CACHE_DATA = payload
        _CACHE_AT = now
        _CACHE_SIGNATURE = current_signature
        _CACHE_LIMIT = fetch_limit
    slim = dict(payload)
    slim["rows"] = payload["rows"][:limit]
    slim["limit"] = limit
    return slim
