"""Stock universe table access (extracted from Storage)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlite3


def upsert_stock_universe(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    source: str,
) -> None:
    if not rows:
        return
    updated_at = datetime.now(timezone.utc).isoformat()
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


def list_stock_universe_symbols(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT symbol FROM stock_universe
        ORDER BY symbol ASC
        """
    ).fetchall()
    return [str(row["symbol"]) for row in rows]


def count_stock_universe(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM stock_universe").fetchone()
    return int(row["n"]) if row else 0


def get_stock_universe_freshness(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT MAX(updated_at) AS updated_at, COUNT(*) AS row_count
        FROM stock_universe
        """
    ).fetchone()
    if not row or not row["updated_at"]:
        return None
    return {"updated_at": str(row["updated_at"]), "row_count": int(row["row_count"] or 0)}


def list_stock_universe(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT symbol, name, exchange, source, updated_at
        FROM stock_universe
        ORDER BY symbol ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]
