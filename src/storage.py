"""SQLite persistence for daily industry snapshots."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.scoring import ScoredIndustry

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    industry_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS industry_daily (
    snapshot_date TEXT NOT NULL,
    industry_key TEXT NOT NULL,
    name TEXT NOT NULL,
    stocks INTEGER NOT NULL,
    perf_w REAL, perf_m REAL, perf_q REAL, perf_h REAL, perf_y REAL,
    rank_w INTEGER, rank_m INTEGER, rank_q INTEGER, rank_h INTEGER, rank_y INTEGER,
    score REAL,
    tier TEXT,
    tags TEXT,
    excluded INTEGER NOT NULL DEFAULT 0,
    exclude_reason TEXT,
    finviz_url TEXT,
    PRIMARY KEY (snapshot_date, industry_key),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_industry_daily_key_date
    ON industry_daily(industry_key, snapshot_date);

CREATE TABLE IF NOT EXISTS industry_stock_picks (
    snapshot_date TEXT NOT NULL,
    industry_key TEXT NOT NULL,
    tickers TEXT NOT NULL,
    screener_url TEXT,
    filters TEXT,
    fetched_at TEXT NOT NULL,
    error TEXT,
    PRIMARY KEY (snapshot_date, industry_key),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(snapshot_date)
);

CREATE TABLE IF NOT EXISTS stock_universe (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    exchange TEXT,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_price_daily (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_price_symbol_date
    ON stock_price_daily(symbol, trade_date);

CREATE TABLE IF NOT EXISTS stock_rs_daily (
    snapshot_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    perf_w REAL NOT NULL,
    perf_m REAL NOT NULL,
    perf_q REAL NOT NULL,
    perf_h REAL NOT NULL,
    perf_y REAL NOT NULL,
    rank_w INTEGER NOT NULL,
    rank_m INTEGER NOT NULL,
    rank_q INTEGER NOT NULL,
    rank_h INTEGER NOT NULL,
    rank_y INTEGER NOT NULL,
    rs_score REAL NOT NULL,
    tier TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, symbol),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_rs_date_score
    ON stock_rs_daily(snapshot_date, rs_score DESC);

CREATE TABLE IF NOT EXISTS stock_watchlist (
    snapshot_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rs_score REAL NOT NULL,
    rs_rank INTEGER NOT NULL,
    industries TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, symbol),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_watchlist_date_rank
    ON stock_watchlist(snapshot_date, rs_rank ASC);

CREATE TABLE IF NOT EXISTS stock_rs_meta (
    snapshot_date TEXT PRIMARY KEY,
    universe_count INTEGER NOT NULL,
    computed_count INTEGER NOT NULL,
    no_bars_count INTEGER NOT NULL,
    insufficient_history_count INTEGER NOT NULL,
    perf_invalid_count INTEGER NOT NULL,
    coverage_ratio REAL NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(snapshot_date)
);

CREATE TABLE IF NOT EXISTS stock_rs_issues (
    snapshot_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    reason TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, symbol),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_rs_issues_date_reason
    ON stock_rs_issues(snapshot_date, reason);
"""


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def save_snapshot(
        self,
        snapshot_date: str,
        scored: list[ScoredIndustry],
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO snapshots(snapshot_date, created_at, industry_count) VALUES (?, ?, ?)",
                (snapshot_date, created_at, len(scored)),
            )
            conn.execute(
                "DELETE FROM industry_daily WHERE snapshot_date = ?",
                (snapshot_date,),
            )
            conn.executemany(
                """
                INSERT INTO industry_daily (
                    snapshot_date, industry_key, name, stocks,
                    perf_w, perf_m, perf_q, perf_h, perf_y,
                    rank_w, rank_m, rank_q, rank_h, rank_y,
                    score, tier, tags, excluded, exclude_reason, finviz_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_date,
                        item.key,
                        item.name,
                        item.stocks,
                        item.perf_w,
                        item.perf_m,
                        item.perf_q,
                        item.perf_h,
                        item.perf_y,
                        item.rank_w,
                        item.rank_m,
                        item.rank_q,
                        item.rank_h,
                        item.rank_y,
                        item.score,
                        item.tier,
                        json.dumps(item.tags, ensure_ascii=False),
                        int(item.excluded),
                        item.exclude_reason,
                        item.finviz_url,
                    )
                    for item in scored
                ],
            )

    def list_snapshot_dates(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT snapshot_date FROM snapshots ORDER BY snapshot_date DESC"
            ).fetchall()
        return [row["snapshot_date"] for row in rows]

    def get_snapshot(self, snapshot_date: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM industry_daily
                WHERE snapshot_date = ?
                ORDER BY score DESC, rank_m ASC
                """,
                (snapshot_date,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_latest_date(self) -> str | None:
        dates = self.list_snapshot_dates()
        return dates[0] if dates else None

    def get_industry_history(
        self,
        industry_key: str,
        metric: str = "rank_m",
    ) -> list[dict[str, Any]]:
        allowed = {
            "rank_w", "rank_m", "rank_q", "rank_h", "rank_y",
            "score", "perf_w", "perf_m", "perf_q", "perf_h", "perf_y",
        }
        if metric not in allowed:
            raise ValueError(f"不支持的 metric: {metric}")

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT snapshot_date, name, {metric} AS value, rank_m, rank_q, rank_h, score, tier, tags
                FROM industry_daily
                WHERE industry_key = ?
                ORDER BY snapshot_date ASC
                """,
                (industry_key,),
            ).fetchall()
        return [dict(row) for row in rows]

    def compare_with_previous(
        self, snapshot_date: str, industry_key: str
    ) -> dict[str, Any] | None:
        dates = self.list_snapshot_dates()
        if snapshot_date not in dates:
            return None
        idx = dates.index(snapshot_date)
        if idx + 1 >= len(dates):
            return None
        prev_date = dates[idx + 1]

        with self._connect() as conn:
            current = conn.execute(
                """
                SELECT rank_w, rank_m, rank_q, rank_h, rank_y, score, tier
                FROM industry_daily
                WHERE snapshot_date = ? AND industry_key = ?
                """,
                (snapshot_date, industry_key),
            ).fetchone()
            previous = conn.execute(
                """
                SELECT rank_w, rank_m, rank_q, rank_h, rank_y, score, tier
                FROM industry_daily
                WHERE snapshot_date = ? AND industry_key = ?
                """,
                (prev_date, industry_key),
            ).fetchone()

        if not current or not previous:
            return None

        return {
            "previous_date": prev_date,
            "rank_m_delta": previous["rank_m"] - current["rank_m"],
            "rank_q_delta": previous["rank_q"] - current["rank_q"],
            "rank_h_delta": previous["rank_h"] - current["rank_h"],
            "score_delta": round(current["score"] - previous["score"], 4),
        }

    def save_industry_stock_picks(
        self,
        snapshot_date: str,
        industry_key: str,
        tickers: list[str],
        screener_url: str,
        filters: str,
        error: str | None = None,
    ) -> None:
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO industry_stock_picks (
                    snapshot_date, industry_key, tickers, screener_url, filters, fetched_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_date,
                    industry_key,
                    json.dumps(tickers, ensure_ascii=False),
                    screener_url,
                    filters,
                    fetched_at,
                    error,
                ),
            )

    def get_industry_stock_picks(
        self, snapshot_date: str, industry_key: str
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM industry_stock_picks
                WHERE snapshot_date = ? AND industry_key = ?
                """,
                (snapshot_date, industry_key),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["tickers"] = json.loads(data["tickers"])
        return data

    def get_stock_picks_for_snapshot(self, snapshot_date: str) -> dict[str, dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM industry_stock_picks
                WHERE snapshot_date = ?
                """,
                (snapshot_date,),
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            data = dict(row)
            data["tickers"] = json.loads(data["tickers"])
            result[data["industry_key"]] = data
        return result

    def upsert_stock_universe(self, rows: list[dict[str, Any]], source: str) -> None:
        if not rows:
            return
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO stock_universe(symbol, name, exchange, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name=excluded.name,
                    exchange=excluded.exchange,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        str(row.get("symbol", "")).upper(),
                        row.get("name") or "",
                        row.get("exchange") or "",
                        source,
                        updated_at,
                    )
                    for row in rows
                    if row.get("symbol")
                ],
            )

    def list_stock_universe_symbols(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol FROM stock_universe
                ORDER BY symbol ASC
                """
            ).fetchall()
        return [str(row["symbol"]) for row in rows]

    def replace_stock_price_history(
        self,
        symbol: str,
        bars: list[dict[str, Any]],
        source: str,
    ) -> None:
        if not bars:
            return
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM stock_price_daily WHERE symbol = ?", (symbol,))
            conn.executemany(
                """
                INSERT OR REPLACE INTO stock_price_daily(
                    symbol, trade_date, close, volume, source, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        symbol,
                        bar["date"],
                        float(bar["close"]),
                        float(bar["volume"]) if bar.get("volume") is not None else None,
                        source,
                        fetched_at,
                    )
                    for bar in bars
                ],
            )

    def save_stock_rs_snapshot(self, snapshot_date: str, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM stock_rs_daily WHERE snapshot_date = ?", (snapshot_date,))
            if rows:
                conn.executemany(
                    """
                    INSERT INTO stock_rs_daily(
                        snapshot_date, symbol, perf_w, perf_m, perf_q, perf_h, perf_y,
                        rank_w, rank_m, rank_q, rank_h, rank_y, rs_score, tier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            snapshot_date,
                            row["symbol"],
                            row["perf_w"],
                            row["perf_m"],
                            row["perf_q"],
                            row["perf_h"],
                            row["perf_y"],
                            row["rank_w"],
                            row["rank_m"],
                            row["rank_q"],
                            row["rank_h"],
                            row["rank_y"],
                            row["rs_score"],
                            row["tier"],
                        )
                        for row in rows
                    ],
                )

    def get_stock_rs_raw(self, snapshot_date: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_date, symbol, perf_w, perf_m, perf_q, perf_h, perf_y,
                       rank_w, rank_m, rank_q, rank_h, rank_y, rs_score, tier
                FROM stock_rs_daily
                WHERE snapshot_date = ?
                ORDER BY rs_score DESC, rank_m ASC
                """,
                (snapshot_date,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_stock_watchlist(self, snapshot_date: str, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM stock_watchlist WHERE snapshot_date = ?", (snapshot_date,))
            if rows:
                conn.executemany(
                    """
                    INSERT INTO stock_watchlist(
                        snapshot_date, symbol, rs_score, rs_rank, industries
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            snapshot_date,
                            row["symbol"],
                            row["rs_score"],
                            row["rs_rank"],
                            json.dumps(row.get("industries", []), ensure_ascii=False),
                        )
                        for row in rows
                    ],
                )

    def get_stock_rs(
        self,
        snapshot_date: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT rs.*, u.name, u.exchange
                FROM stock_rs_daily rs
                LEFT JOIN stock_universe u ON u.symbol = rs.symbol
                WHERE rs.snapshot_date = ?
                ORDER BY rs.rs_score DESC, rs.rank_m ASC
                LIMIT ?
                """,
                (snapshot_date, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_stock_watchlist(
        self,
        snapshot_date: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT w.*, u.name, u.exchange
                FROM stock_watchlist w
                LEFT JOIN stock_universe u ON u.symbol = w.symbol
                WHERE w.snapshot_date = ?
                ORDER BY w.rs_rank ASC
                LIMIT ?
                """,
                (snapshot_date, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["industries"] = json.loads(data.get("industries") or "[]")
            result.append(data)
        return result

    def count_stock_rs(self, snapshot_date: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM stock_rs_daily
                WHERE snapshot_date = ?
                """,
                (snapshot_date,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def count_stock_watchlist(self, snapshot_date: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM stock_watchlist
                WHERE snapshot_date = ?
                """,
                (snapshot_date,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def save_stock_rs_meta(self, snapshot_date: str, meta: dict[str, Any]) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO stock_rs_meta(
                    snapshot_date, universe_count, computed_count, no_bars_count,
                    insufficient_history_count, perf_invalid_count, coverage_ratio, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_date,
                    int(meta.get("universe_count", 0)),
                    int(meta.get("computed_count", 0)),
                    int(meta.get("no_bars_count", 0)),
                    int(meta.get("insufficient_history_count", 0)),
                    int(meta.get("perf_invalid_count", 0)),
                    float(meta.get("coverage_ratio", 0.0)),
                    updated_at,
                ),
            )

    def get_stock_rs_meta(self, snapshot_date: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM stock_rs_meta
                WHERE snapshot_date = ?
                """,
                (snapshot_date,),
            ).fetchone()
        return dict(row) if row else None

    def save_stock_rs_issues(self, snapshot_date: str, issues: dict[str, str]) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM stock_rs_issues WHERE snapshot_date = ?", (snapshot_date,))
            if issues:
                conn.executemany(
                    """
                    INSERT INTO stock_rs_issues(snapshot_date, symbol, reason, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (snapshot_date, symbol, reason, updated_at)
                        for symbol, reason in issues.items()
                    ],
                )

    def get_stock_rs_issues(self, snapshot_date: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, reason
                FROM stock_rs_issues
                WHERE snapshot_date = ?
                """,
                (snapshot_date,),
            ).fetchall()
        return {str(row["symbol"]): str(row["reason"]) for row in rows}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        tags = data.get("tags")
        if isinstance(tags, str):
            try:
                data["tags"] = json.loads(tags)
            except json.JSONDecodeError:
                data["tags"] = []
        data["excluded"] = bool(data.get("excluded"))
        return data


def today_snapshot_date() -> str:
    return date.today().isoformat()
