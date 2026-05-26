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

CREATE TABLE IF NOT EXISTS snapshot_runs (
    snapshot_date TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    current_step TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS rs_job_runs (
    job_id TEXT PRIMARY KEY,
    snapshot_date TEXT NOT NULL,
    job_kind TEXT NOT NULL DEFAULT 'main',
    status TEXT NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT,
    result_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_rs_job_runs_snapshot_started
    ON rs_job_runs(snapshot_date, started_at DESC);

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

CREATE TABLE IF NOT EXISTS stock_rs_new_daily (
    snapshot_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    cohort TEXT NOT NULL,
    bar_count INTEGER NOT NULL,
    perf_w REAL,
    perf_m REAL,
    perf_q REAL,
    perf_h REAL,
    perf_tq REAL,
    rank_w INTEGER,
    rank_m INTEGER,
    rank_q INTEGER,
    rank_h INTEGER,
    rank_tq INTEGER,
    rs_score REAL NOT NULL,
    tier TEXT NOT NULL,
    in_leaderboard INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (snapshot_date, symbol),
    FOREIGN KEY (snapshot_date) REFERENCES snapshots(snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_rs_new_date_cohort
    ON stock_rs_new_daily(snapshot_date, cohort, rs_score DESC);

CREATE TABLE IF NOT EXISTS breadth_sheet_meta (
    sheet_gid TEXT PRIMARY KEY,
    sheet_name TEXT NOT NULL,
    first_date TEXT,
    last_date TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    last_sync_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS breadth_raw_daily (
    trade_date TEXT NOT NULL,
    raw_date TEXT,
    sheet_gid TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    c1 REAL, c2 REAL, c3 REAL, c4 REAL, c5 REAL, c6 REAL, c7 REAL, c8 REAL,
    c9 REAL, c10 REAL, c11 REAL, c12 REAL, c13 REAL, c14 REAL, c15 REAL,
    raw_values TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, sheet_gid)
);

CREATE INDEX IF NOT EXISTS idx_breadth_raw_date
    ON breadth_raw_daily(trade_date);

CREATE TABLE IF NOT EXISTS breadth_daily (
    trade_date TEXT PRIMARY KEY,
    raw_date TEXT,
    sheet_gid TEXT NOT NULL,
    c1 REAL, c2 REAL, c3 REAL, c4 REAL, c5 REAL, c6 REAL, c7 REAL, c8 REAL,
    c9 REAL, c10 REAL, c11 REAL, c12 REAL, c13 REAL, c14 REAL, c15 REAL,
    raw_values TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS breadth_threshold_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_stock_rs_meta(conn)
            self._migrate_rs_job_runs(conn)

    def _migrate_stock_rs_meta(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(stock_rs_meta)").fetchall()}
        additions = [
            ("new_stock_m_count", "INTEGER NOT NULL DEFAULT 0"),
            ("new_stock_q_count", "INTEGER NOT NULL DEFAULT 0"),
            ("new_stock_h_count", "INTEGER NOT NULL DEFAULT 0"),
            ("new_stock_3q_count", "INTEGER NOT NULL DEFAULT 0"),
            ("new_stock_leaderboard_count", "INTEGER NOT NULL DEFAULT 0"),
            ("new_stock_watchlist_added", "INTEGER NOT NULL DEFAULT 0"),
        ]
        for name, typedef in additions:
            if name not in cols:
                conn.execute(f"ALTER TABLE stock_rs_meta ADD COLUMN {name} {typedef}")

    def _migrate_rs_job_runs(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(rs_job_runs)").fetchall()}
        if "job_kind" not in cols:
            conn.execute("ALTER TABLE rs_job_runs ADD COLUMN job_kind TEXT NOT NULL DEFAULT 'main'")

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

    def upsert_snapshot_run(
        self,
        snapshot_date: str,
        status: str,
        *,
        current_step: str | None = None,
        error: str | None = None,
        details: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT started_at
                FROM snapshot_runs
                WHERE snapshot_date = ?
                """,
                (snapshot_date,),
            ).fetchone()
            started_at = str(existing["started_at"]) if existing and existing["started_at"] else now
            conn.execute(
                """
                INSERT OR REPLACE INTO snapshot_runs(
                    snapshot_date, status, current_step, started_at, updated_at,
                    finished_at, error, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_date,
                    status,
                    current_step,
                    started_at,
                    now,
                    now if finished else None,
                    error,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )

    def get_snapshot_run(self, snapshot_date: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM snapshot_runs
                WHERE snapshot_date = ?
                """,
                (snapshot_date,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["details"] = json.loads(data.get("details") or "{}")
        except json.JSONDecodeError:
            data["details"] = {}
        return data

    def upsert_rs_job_run(
        self,
        job_id: str,
        snapshot_date: str,
        status: str,
        *,
        job_kind: str = "main",
        processed: int = 0,
        total: int = 0,
        error: str | None = None,
        result: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT started_at
                FROM rs_job_runs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            started_at = str(existing["started_at"]) if existing and existing["started_at"] else now
            conn.execute(
                """
                INSERT OR REPLACE INTO rs_job_runs(
                    job_id, snapshot_date, job_kind, status, processed, total,
                    started_at, updated_at, finished_at, error, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    snapshot_date,
                    job_kind,
                    status,
                    int(processed),
                    int(total),
                    started_at,
                    now,
                    now if finished else None,
                    error,
                    json.dumps(result or {}, ensure_ascii=False),
                ),
            )

    def get_latest_rs_job_run(self, snapshot_date: str, *, job_kind: str = "main") -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM rs_job_runs
                WHERE snapshot_date = ? AND job_kind = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (snapshot_date, job_kind),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["result"] = json.loads(data.get("result_json") or "{}")
        except json.JSONDecodeError:
            data["result"] = {}
        return data

    def claim_rs_job_run(
        self,
        job_id: str,
        snapshot_date: str,
        job_kind: str,
        *,
        stale_seconds: int,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Atomically claim an RS job slot; returns (claimed, blocking_job)."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT *
                FROM rs_job_runs
                WHERE snapshot_date = ? AND job_kind = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (snapshot_date, job_kind),
            ).fetchone()
            if row:
                active = dict(row)
                status = str(active.get("status") or "")
                if status in {"running", "cancelling"}:
                    age_seconds = stale_seconds + 1
                    try:
                        updated = datetime.fromisoformat(str(active["updated_at"]))
                        age_seconds = (now - updated).total_seconds()
                    except ValueError:
                        pass
                    if age_seconds <= stale_seconds:
                        conn.execute("ROLLBACK")
                        data = dict(active)
                        try:
                            data["result"] = json.loads(data.get("result_json") or "{}")
                        except json.JSONDecodeError:
                            data["result"] = {}
                        return False, data
                    conn.execute(
                        """
                        UPDATE rs_job_runs
                        SET status = 'error',
                            error = ?,
                            updated_at = ?,
                            finished_at = ?
                        WHERE job_id = ?
                        """,
                        (
                            f"stale job timeout>{stale_seconds}s",
                            now_iso,
                            now_iso,
                            active["job_id"],
                        ),
                    )
            conn.execute(
                """
                INSERT INTO rs_job_runs(
                    job_id, snapshot_date, job_kind, status, processed, total,
                    started_at, updated_at, finished_at, error, result_json
                ) VALUES (?, ?, ?, 'running', 0, 0, ?, ?, NULL, NULL, '{}')
                """,
                (job_id, snapshot_date, job_kind, now_iso, now_iso),
            )
            conn.commit()
        return True, None

    def compare_all_with_previous(self, snapshot_date: str) -> dict[str, dict[str, Any] | None]:
        dates = self.list_snapshot_dates()
        if snapshot_date not in dates:
            return {}
        idx = dates.index(snapshot_date)
        if idx + 1 >= len(dates):
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT industry_key
                    FROM industry_daily
                    WHERE snapshot_date = ?
                    """,
                    (snapshot_date,),
                ).fetchall()
            return {str(r["industry_key"]): None for r in rows}
        prev_date = dates[idx + 1]

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.industry_key,
                    c.rank_m AS c_rank_m, c.rank_q AS c_rank_q, c.rank_h AS c_rank_h, c.score AS c_score,
                    p.rank_m AS p_rank_m, p.rank_q AS p_rank_q, p.rank_h AS p_rank_h, p.score AS p_score
                FROM industry_daily c
                LEFT JOIN industry_daily p
                  ON p.snapshot_date = ? AND p.industry_key = c.industry_key
                WHERE c.snapshot_date = ?
                """,
                (prev_date, snapshot_date),
            ).fetchall()
        out: dict[str, dict[str, Any] | None] = {}
        for row in rows:
            key = str(row["industry_key"])
            if row["p_rank_m"] is None:
                out[key] = None
                continue
            out[key] = {
                "previous_date": prev_date,
                "rank_m_delta": int(row["p_rank_m"]) - int(row["c_rank_m"]),
                "rank_q_delta": int(row["p_rank_q"]) - int(row["c_rank_q"]),
                "rank_h_delta": int(row["p_rank_h"]) - int(row["c_rank_h"]),
                "score_delta": round(float(row["c_score"]) - float(row["p_score"]), 4),
            }
        return out

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
        return self.compare_all_with_previous(snapshot_date).get(industry_key)

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

    def get_latest_successful_industry_stock_picks(
        self,
        industry_key: str,
        *,
        before_snapshot_date: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any] | None:
        """最近一次成功抓取（无 error、tickers 非空）的行业筛股结果。"""
        query = """
            SELECT *
            FROM industry_stock_picks
            WHERE industry_key = ?
              AND (error IS NULL OR TRIM(error) = '')
        """
        params: list[Any] = [industry_key]
        if before_snapshot_date:
            query += " AND snapshot_date < ?"
            params.append(before_snapshot_date)
        query += " ORDER BY snapshot_date DESC, fetched_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        for row in rows:
            data = dict(row)
            try:
                tickers = json.loads(data.get("tickers") or "[]")
            except json.JSONDecodeError:
                tickers = []
            if tickers:
                data["tickers"] = tickers
                return data
        return None

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
            self._migrate_stock_rs_meta(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO stock_rs_meta(
                    snapshot_date, universe_count, computed_count, no_bars_count,
                    insufficient_history_count, perf_invalid_count, coverage_ratio,
                    new_stock_m_count, new_stock_q_count, new_stock_h_count,
                    new_stock_3q_count, new_stock_leaderboard_count,
                    new_stock_watchlist_added, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_date,
                    int(meta.get("universe_count", 0)),
                    int(meta.get("computed_count", 0)),
                    int(meta.get("no_bars_count", 0)),
                    int(meta.get("insufficient_history_count", 0)),
                    int(meta.get("perf_invalid_count", 0)),
                    float(meta.get("coverage_ratio", 0.0)),
                    int(meta.get("new_stock_m_count", 0)),
                    int(meta.get("new_stock_q_count", 0)),
                    int(meta.get("new_stock_h_count", 0)),
                    int(meta.get("new_stock_3q_count", 0)),
                    int(meta.get("new_stock_leaderboard_count", 0)),
                    int(meta.get("new_stock_watchlist_added", 0)),
                    updated_at,
                ),
            )

    def save_stock_rs_new_snapshot(self, snapshot_date: str, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM stock_rs_new_daily WHERE snapshot_date = ?", (snapshot_date,))
            if not rows:
                return
            conn.executemany(
                """
                INSERT INTO stock_rs_new_daily(
                    snapshot_date, symbol, cohort, bar_count,
                    perf_w, perf_m, perf_q, perf_h, perf_tq,
                    rank_w, rank_m, rank_q, rank_h, rank_tq,
                    rs_score, tier, in_leaderboard
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_date,
                        row["symbol"],
                        row["cohort"],
                        int(row["bar_count"]),
                        row.get("perf_w"),
                        row.get("perf_m"),
                        row.get("perf_q"),
                        row.get("perf_h"),
                        row.get("perf_tq"),
                        row.get("rank_w"),
                        row.get("rank_m"),
                        row.get("rank_q"),
                        row.get("rank_h"),
                        row.get("rank_tq"),
                        row["rs_score"],
                        row["tier"],
                        1 if row.get("in_leaderboard") else 0,
                    )
                    for row in rows
                ],
            )

    def get_stock_rs_new(
        self,
        snapshot_date: str,
        *,
        cohort: str | None = None,
        leaderboard_only: bool = False,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses = ["snapshot_date = ?"]
        params: list[Any] = [snapshot_date]
        if cohort:
            clauses.append("cohort = ?")
            params.append(cohort)
        if leaderboard_only:
            clauses.append("in_leaderboard = 1")
        params.append(limit)
        sql = f"""
            SELECT n.*, u.name, u.exchange
            FROM stock_rs_new_daily n
            LEFT JOIN stock_universe u ON u.symbol = n.symbol
            WHERE {' AND '.join(clauses)}
            ORDER BY n.cohort ASC, n.rs_score DESC, n.symbol ASC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count_stock_rs_new(self, snapshot_date: str, *, leaderboard_only: bool = False) -> int:
        with self._connect() as conn:
            if leaderboard_only:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM stock_rs_new_daily
                    WHERE snapshot_date = ? AND in_leaderboard = 1
                    """,
                    (snapshot_date,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM stock_rs_new_daily
                    WHERE snapshot_date = ?
                    """,
                    (snapshot_date,),
                ).fetchone()
        return int(row["n"]) if row else 0

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

    def upsert_breadth_sheet_meta(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        synced_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO breadth_sheet_meta(
                    sheet_gid, sheet_name, first_date, last_date, row_count, last_sync_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sheet_gid) DO UPDATE SET
                    sheet_name=excluded.sheet_name,
                    first_date=excluded.first_date,
                    last_date=excluded.last_date,
                    row_count=excluded.row_count,
                    last_sync_at=excluded.last_sync_at
                """,
                [
                    (
                        str(row.get("sheet_gid")),
                        str(row.get("sheet_name") or f"gid_{row.get('sheet_gid')}"),
                        row.get("first_date"),
                        row.get("last_date"),
                        int(row.get("row_count") or 0),
                        synced_at,
                    )
                    for row in rows
                ],
            )

    def clear_breadth_history(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM breadth_raw_daily")
            conn.execute("DELETE FROM breadth_sheet_meta")
            conn.execute("DELETE FROM breadth_daily")

    def save_breadth_raw_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        ingested_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO breadth_raw_daily(
                    trade_date, raw_date, sheet_gid, sheet_name,
                    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15,
                    raw_values, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["trade_date"],
                        row.get("raw_date"),
                        row["sheet_gid"],
                        row.get("sheet_name") or f"gid_{row['sheet_gid']}",
                        row.get("c1"),
                        row.get("c2"),
                        row.get("c3"),
                        row.get("c4"),
                        row.get("c5"),
                        row.get("c6"),
                        row.get("c7"),
                        row.get("c8"),
                        row.get("c9"),
                        row.get("c10"),
                        row.get("c11"),
                        row.get("c12"),
                        row.get("c13"),
                        row.get("c14"),
                        row.get("c15"),
                        json.dumps(row.get("raw_values") or {}, ensure_ascii=False),
                        ingested_at,
                    )
                    for row in rows
                ],
            )

    def rebuild_breadth_daily_from_raw(self) -> int:
        primary_gid = "1082103394"
        with self._connect() as conn:
            raw_rows = conn.execute(
                """
                SELECT *
                FROM breadth_raw_daily
                ORDER BY trade_date ASC, sheet_gid ASC
                """
            ).fetchall()

            def _row_score(item: dict[str, Any]) -> int:
                return sum(1 for i in range(1, 16) if item.get(f"c{i}") is not None)

            def _prefer_row(candidate: dict[str, Any], incumbent: dict[str, Any]) -> bool:
                cand_gid = str(candidate.get("sheet_gid") or "")
                inc_gid = str(incumbent.get("sheet_gid") or "")
                if cand_gid == primary_gid and inc_gid != primary_gid:
                    return True
                if inc_gid == primary_gid and cand_gid != primary_gid:
                    return False
                return _row_score(candidate) > _row_score(incumbent)

            best_by_date: dict[str, dict[str, Any]] = {}
            for rr in raw_rows:
                row = dict(rr)
                date_key = str(row["trade_date"])
                prev = best_by_date.get(date_key)
                if not prev or _prefer_row(row, prev):
                    best_by_date[date_key] = row

            updated_at = datetime.now(timezone.utc).isoformat()
            conn.execute("DELETE FROM breadth_daily")
            conn.executemany(
                """
                INSERT INTO breadth_daily(
                    trade_date, raw_date, sheet_gid,
                    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15,
                    raw_values, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["trade_date"],
                        row.get("raw_date"),
                        row["sheet_gid"],
                        row.get("c1"),
                        row.get("c2"),
                        row.get("c3"),
                        row.get("c4"),
                        row.get("c5"),
                        row.get("c6"),
                        row.get("c7"),
                        row.get("c8"),
                        row.get("c9"),
                        row.get("c10"),
                        row.get("c11"),
                        row.get("c12"),
                        row.get("c13"),
                        row.get("c14"),
                        row.get("c15"),
                        row.get("raw_values") or "{}",
                        updated_at,
                    )
                    for _, row in sorted(best_by_date.items(), key=lambda x: x[0])
                ],
            )
        return len(best_by_date)

    def get_breadth_daily(
        self,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM breadth_daily
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            row = dict(r)
            try:
                row["raw_values"] = json.loads(row.get("raw_values") or "{}")
            except json.JSONDecodeError:
                row["raw_values"] = {}
            result.append(row)
        return result

    def get_breadth_sheet_meta(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM breadth_sheet_meta
                ORDER BY last_date DESC, sheet_gid ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def get_breadth_coverage(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    MIN(trade_date) AS first_date,
                    MAX(trade_date) AS last_date,
                    COUNT(*) AS row_count
                FROM breadth_daily
                """
            ).fetchone()
            sheet_row = conn.execute(
                "SELECT COUNT(*) AS n FROM breadth_sheet_meta"
            ).fetchone()
        return {
            "first_date": row["first_date"] if row else None,
            "last_date": row["last_date"] if row else None,
            "row_count": int(row["row_count"]) if row else 0,
            "sheet_count": int(sheet_row["n"]) if sheet_row else 0,
        }

    def get_breadth_cache_signature(self) -> str:
        """用于页面缓存失效：数据行数 + 最新日期 + 最新更新时间 + sheet 行数。"""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS row_count,
                    MAX(trade_date) AS last_date,
                    MAX(updated_at) AS last_updated
                FROM breadth_daily
                """
            ).fetchone()
            sheet_row = conn.execute(
                "SELECT COUNT(*) AS n FROM breadth_sheet_meta"
            ).fetchone()
        row_count = int(row["row_count"]) if row else 0
        last_date = str(row["last_date"] or "") if row else ""
        last_updated = str(row["last_updated"] or "") if row else ""
        sheet_count = int(sheet_row["n"]) if sheet_row else 0
        return f"{row_count}|{last_date}|{last_updated}|{sheet_count}"

    def get_breadth_threshold_overrides(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value
                FROM breadth_threshold_config
                """
            ).fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            key = str(row["key"])
            value = row["value"]
            try:
                result[key] = float(value)
            except (TypeError, ValueError):
                result[key] = value
        return result

    def save_breadth_threshold_overrides(self, payload: dict[str, Any]) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO breadth_threshold_config(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                [
                    (str(k), str(v), updated_at)
                    for k, v in payload.items()
                ],
            )

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
