"""Finviz Elite export engine — full-market overview + performance CSV pulls."""

from __future__ import annotations

import csv
import http.cookiejar
import io
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from src.logging_config import get_logger

logger = get_logger(__name__)

ELITE_HOST = "https://elite.finviz.com"
ELITE_EXPORT_PATH = "/export.ashx"
FINVIZ_HOME = "https://finviz.com/"
DEFAULT_US_FILTER = "geo_usa"
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_ROOT = Path(__file__).resolve().parent.parent.parent

_PERF_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "perf_week": ("Performance (Week)", "Perf Week"),
    "perf_month": ("Performance (Month)", "Perf Month"),
    "perf_quarter": ("Performance (Quarter)", "Perf Quarter", "Perf Quart"),
    "perf_half": ("Performance (Half Year)", "Perf Half"),
    "perf_year": ("Performance (Year)", "Performance (YTD)", "Perf Year", "Perf YTD"),
    "rel_volume": ("Relative Volume", "Rel Volume"),
    "volatility_w": ("Volatility (Week)", "Volatility W", "Volatility Week"),
    "volatility_m": ("Volatility (Month)", "Volatility M", "Volatility Month"),
}

_TECH_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "sma20": ("SMA20", "20-Day Simple Moving Average", "20-SMA"),
    "sma50": ("SMA50", "50-Day Simple Moving Average", "50-SMA"),
    "sma200": ("SMA200", "200-Day Simple Moving Average", "200-SMA"),
    "volume": ("Volume",),
}


def elite_auth_key() -> str | None:
    key = (os.getenv("FINVIZ_AUTH_KEY") or os.getenv("FINVIZ_ELITE_AUTH") or "").strip()
    return key or None


def elite_market_filter() -> str:
    return (os.getenv("FINVIZ_ELITE_FILTER") or DEFAULT_US_FILTER).strip() or DEFAULT_US_FILTER


def _cookie_file_path() -> str:
    env_path = (os.getenv("FINVIZ_COOKIE_FILE") or "").strip()
    if env_path and Path(env_path).is_file():
        return env_path
    default = _ROOT / "data" / "finviz_cookies.txt"
    return str(default) if default.is_file() else ""


def _load_cookie_jar(cookie_file: str) -> http.cookiejar.MozillaCookieJar | None:
    path = Path(cookie_file)
    if not path.is_file():
        return None
    jar = http.cookiejar.MozillaCookieJar(str(path))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except OSError:
        return None
    return jar


def _url_has_auth_param(url: str) -> bool:
    return bool((parse_qs(urlparse(url).query).get("auth") or [""])[0].strip())


def build_elite_export_url(*, view: str, auth_key: str, filters: str | None = None) -> str:
    filt = filters if filters is not None else elite_market_filter()
    return f"{ELITE_HOST}{ELITE_EXPORT_PATH}?v={view}&f={filt}&auth={auth_key}"


def _pick(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for name in aliases:
        val = row.get(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _parse_csv(text: str) -> list[dict[str, str]]:
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _fetch_with_curl(url: str, *, timeout: int, use_cookies: bool) -> tuple[str, str]:
    cookie_file = _cookie_file_path() if use_cookies else ""
    cmd = [
        "curl",
        "-sL",
        "--max-time",
        str(timeout),
        "--retry",
        "2",
        "--retry-delay",
        "1",
        "--retry-all-errors",
        "--compressed",
        "-A",
        _DEFAULT_USER_AGENT,
        "-e",
        FINVIZ_HOME,
        "-H",
        "Accept: text/csv,text/plain,*/*",
        "-w",
        "\n__FINAL_URL__%{url_effective}",
    ]
    if cookie_file:
        cmd.extend(["-b", cookie_file])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"curl exit {result.returncode}")
    body, _, tail = result.stdout.rpartition("\n__FINAL_URL__")
    final_url = tail.strip() if tail else url
    if not body.strip():
        raise RuntimeError("curl returned empty body")
    return body, final_url


def _fetch_with_requests(url: str, *, timeout: int, use_cookies: bool) -> tuple[str, str]:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": _DEFAULT_USER_AGENT,
            "Accept": "text/csv,text/plain,*/*",
            "Referer": f"{ELITE_HOST}/screener.ashx",
        }
    )
    if use_cookies:
        cookie_file = _cookie_file_path()
        if cookie_file:
            jar = _load_cookie_jar(cookie_file)
            if jar is not None:
                session.cookies = jar
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text, str(response.url)


def _validate_export_body(text: str, *, final_url: str, label: str) -> None:
    lowered_url = final_url.lower()
    if lowered_url.rstrip("/").endswith("/elite"):
        raise RuntimeError(
            f"Elite {label}: redirected to Elite marketing/login page — "
            "regenerate API token at elite.finviz.com (Settings → API)"
        )
    if _looks_like_html_error(text):
        raise RuntimeError(
            f"Elite {label}: response is HTML, not CSV — check FINVIZ_AUTH_KEY"
        )
    rows = _parse_csv(text)
    if not rows:
        raise RuntimeError(f"Elite {label}: CSV parsed to zero rows")
    first = rows[0]
    if "Ticker" not in first and "ticker" not in first:
        raise RuntimeError(
            f"Elite {label}: CSV missing Ticker column (headers={list(first.keys())[:8]})"
        )


def _export_label(url: str) -> str:
    if "v=111" in url:
        return "overview"
    if "v=141" in url:
        return "performance"
    if "v=171" in url:
        return "technical"
    return "export"


def _fetch_export_text(url: str, *, timeout: int = 60, max_retries: int = 3) -> str:
    label = _export_label(url)
    # Elite export auth= token is sufficient; Netscape cookie file must not be raw-set as header.
    use_cookies = not _url_has_auth_param(url)
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            text, final_url = _fetch_with_curl(url, timeout=timeout, use_cookies=use_cookies)
            _validate_export_body(text, final_url=final_url, label=label)
            logger.info(
                "Elite %s export via curl OK (%d bytes, final=%s)",
                label,
                len(text),
                final_url,
            )
            return text
        except (OSError, RuntimeError) as exc:
            last_error = exc
            logger.debug("Elite %s curl attempt %d failed: %s", label, attempt + 1, exc)
        try:
            text, final_url = _fetch_with_requests(url, timeout=timeout, use_cookies=use_cookies)
            _validate_export_body(text, final_url=final_url, label=label)
            logger.info("Elite %s export via requests OK (%d bytes)", label, len(text))
            return text
        except (requests.RequestException, OSError, RuntimeError) as exc:
            last_error = exc
            logger.debug("Elite %s requests attempt %d failed: %s", label, attempt + 1, exc)
        if attempt < max_retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Elite {label} export failed: {last_error}")


def _export_urls_from_env(auth_key: str) -> tuple[str, str] | None:
    """Optional override: paste full export URLs from Elite screener."""
    overview = (os.getenv("FINVIZ_ELITE_EXPORT_OVERVIEW_URL") or "").strip()
    perf = (os.getenv("FINVIZ_ELITE_EXPORT_PERF_URL") or "").strip()
    if overview and perf:
        return overview, perf
    single = (os.getenv("FINVIZ_ELITE_EXPORT_URL") or "").strip()
    if single:
        parsed = urlparse(single)
        qs = parse_qs(parsed.query)
        view = (qs.get("v") or ["111"])[0]
        perf_view = "141" if view == "111" else view
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        filt = (qs.get("f") or [elite_market_filter()])[0]
        return (
            f"{base}?v=111&f={filt}&auth={auth_key}",
            f"{base}?v=141&f={filt}&auth={auth_key}",
        )
    return None


def fetch_elite_market_data(
    *,
    auth_key: str | None = None,
    timeout: int = 60,
) -> dict[str, dict[str, Any]] | None:
    """
    Pull full-market Finviz Elite CSV exports (overview + performance).

    Returns symbol -> fields dict, or None to signal fallback to Yahoo/free path.
    """
    key = auth_key or elite_auth_key()
    if not key:
        logger.info("FINVIZ_AUTH_KEY not set; skipping Elite engine")
        return None

    fetch_technical = (os.getenv("FINVIZ_ELITE_FETCH_TECHNICAL") or "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    logger.info(
        "Elite engine: fetching overview + performance%s (host=%s, filter=%s)",
        " + technical" if fetch_technical else "",
        ELITE_HOST,
        elite_market_filter(),
    )

    url_pair = _export_urls_from_env(key)
    if url_pair:
        url_overview, url_perf = url_pair
        url_technical = build_elite_export_url(
            view="171",
            auth_key=key,
            filters=elite_market_filter(),
        )
    else:
        filt = elite_market_filter()
        url_overview = build_elite_export_url(view="111", auth_key=key, filters=filt)
        url_perf = build_elite_export_url(view="141", auth_key=key, filters=filt)
        url_technical = build_elite_export_url(view="171", auth_key=key, filters=filt)

    try:
        text_ov = _fetch_export_text(url_overview, timeout=timeout)
        time.sleep(1.0)  # Elite recommends <= 1 req / 60s; brief pause between views
        text_pf = _fetch_export_text(url_perf, timeout=timeout)
        text_tech = ""
        if fetch_technical:
            time.sleep(1.0)
            text_tech = _fetch_export_text(url_technical, timeout=timeout)
    except RuntimeError as exc:
        logger.warning("%s; falling back to free path", exc)
        return None

    overview_rows = _parse_csv(text_ov)
    perf_rows = _parse_csv(text_pf)
    tech_rows = _parse_csv(text_tech) if text_tech else []
    if not overview_rows:
        logger.warning("Elite overview CSV empty; falling back")
        return None

    market_data: dict[str, dict[str, Any]] = {}
    for row in overview_rows:
        ticker = str(row.get("Ticker") or row.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        market_data[ticker] = {
            "symbol": ticker,
            "industry": row.get("Industry", "") or "",
            "sector": row.get("Sector", "") or "",
            "market_cap": row.get("Market Cap", "") or "",
            "price": row.get("Price", "") or "",
            "volume": _pick(row, _TECH_FIELD_ALIASES["volume"]),
        }

    for row in perf_rows:
        ticker = str(row.get("Ticker") or row.get("ticker") or "").upper().strip()
        if not ticker or ticker not in market_data:
            continue
        market_data[ticker].update(
            {
                "perf_week": _pick(row, _PERF_FIELD_ALIASES["perf_week"]),
                "perf_month": _pick(row, _PERF_FIELD_ALIASES["perf_month"]),
                "perf_quarter": _pick(row, _PERF_FIELD_ALIASES["perf_quarter"]),
                "perf_half": _pick(row, _PERF_FIELD_ALIASES["perf_half"]),
                "perf_year": _pick(row, _PERF_FIELD_ALIASES["perf_year"]),
                "rel_volume": _pick(row, _PERF_FIELD_ALIASES["rel_volume"]),
                "volatility_w": _pick(row, _PERF_FIELD_ALIASES["volatility_w"]),
                "volatility_m": _pick(row, _PERF_FIELD_ALIASES["volatility_m"]),
            }
        )

    for row in tech_rows:
        ticker = str(row.get("Ticker") or row.get("ticker") or "").upper().strip()
        if not ticker or ticker not in market_data:
            continue
        market_data[ticker].update(
            {
                "sma20": _pick(row, _TECH_FIELD_ALIASES["sma20"]),
                "sma50": _pick(row, _TECH_FIELD_ALIASES["sma50"]),
                "sma200": _pick(row, _TECH_FIELD_ALIASES["sma200"]),
            }
        )
        if not market_data[ticker].get("volume"):
            market_data[ticker]["volume"] = _pick(row, _TECH_FIELD_ALIASES["volume"])

    with_perf = sum(1 for row in market_data.values() if row.get("perf_month"))
    with_tech = sum(1 for row in market_data.values() if row.get("sma20"))
    logger.info(
        "Elite engine loaded %d symbols (%d with performance, %d with SMA fields)",
        len(market_data),
        with_perf,
        with_tech,
    )
    return market_data


def _looks_like_html_error(text: str) -> bool:
    head = (text or "")[:800].lstrip().lower()
    if head.startswith("ticker,") or head.startswith("no.,ticker"):
        return False
    return head.startswith("<!doctype html") or head.startswith("<html")


def parse_finviz_number(value: Any) -> float | None:
    """Parse Finviz numeric cells (prices, volumes) with commas."""
    text = str(value or "").strip().replace(",", "")
    if not text or text in ("-", "—", "N/A"):
        return None
    multipliers = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    suffix = text[-1].upper()
    if suffix in multipliers:
        try:
            return float(text[:-1]) * multipliers[suffix]
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_finviz_percent(value: Any) -> float | None:
    """Parse Finviz percent cells like ``-3.26%`` or plain floats."""
    text = str(value or "").strip().replace(",", "")
    if not text or text in ("-", "—", "N/A"):
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


_ELITE_TO_RS_PERF: tuple[tuple[str, str], ...] = (
    ("perf_w", "perf_week"),
    ("perf_m", "perf_month"),
    ("perf_q", "perf_quarter"),
    ("perf_h", "perf_half"),
    ("perf_y", "perf_year"),
)


def elite_row_to_perf(symbol: str, row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map one Elite market row to stock_rs perf_map entry (all five horizons required)."""
    if not row:
        return None
    sym = str(symbol or row.get("symbol") or "").upper().strip()
    if not sym:
        return None
    perf: dict[str, Any] = {"symbol": sym}
    for rs_key, elite_key in _ELITE_TO_RS_PERF:
        parsed = parse_finviz_percent(row.get(elite_key))
        if parsed is None:
            return None
        perf[rs_key] = parsed
    return perf


def elite_row_for_symbol(
    market_data: dict[str, dict[str, Any]],
    symbol: str,
) -> dict[str, Any] | None:
    """Lookup Elite row; tolerate BRK-B vs BRK.B style ticker differences."""
    sym = str(symbol or "").upper().strip()
    if not sym:
        return None
    row = market_data.get(sym)
    if row:
        return row
    if "-" in sym:
        row = market_data.get(sym.replace("-", "."))
        if row:
            return row
    if "." in sym:
        row = market_data.get(sym.replace(".", "-"))
        if row:
            return row
    return None


def passes_elite_swing_filters(
    row: dict[str, Any],
    rs_score: float,
    *,
    min_rs_score: float = 0.8,
    min_daily_dollar_volume: float = 15_000_000.0,
) -> bool:
    """
    Minervini-style trend stack + liquidity using Finviz SMA distance columns.

    SMA fields are % distance of price above/below each moving average.

    Relaxed Swing Trader thresholds:
    - RS >= 80 (top 20% in strong industry)
    - Daily turnover >= $15M (wide enough for mid-cap momentum)
    - Trend: price > SMA50 > SMA200 (Stage 2 uptrend, allows SMA20 pullbacks)
    """
    if rs_score < min_rs_score:
        return False
    price = parse_finviz_number(row.get("price"))
    volume = parse_finviz_number(row.get("volume"))
    if price is None or volume is None or price * volume < min_daily_dollar_volume:
        return False
    sma50 = parse_finviz_percent(row.get("sma50"))
    sma200 = parse_finviz_percent(row.get("sma200"))
    if sma50 is None or sma200 is None:
        return False
    # Stage 2 uptrend: price above SMA50 above SMA200
    # (sma200 % > sma50 % > 0 → price furthest above SMA200 = golden cross zone)
    if not (sma200 > sma50 > 0):
        return False
    return True


def build_perf_map_from_elite(
    market_data: dict[str, dict[str, Any]],
    symbols: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build perf_map entries for symbols Elite can cover; return symbols still needing Yahoo."""
    perf_map: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for sym in symbols:
        row = elite_row_for_symbol(market_data, sym)
        perf = elite_row_to_perf(sym, row)
        if perf:
            perf_map[sym] = perf
        else:
            missing.append(sym)
    return perf_map, missing
