from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional

DB_PATH = Path(__file__).resolve().parent / "data.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[dict]:
    return [dict(row) for row in rows]


def fetchall(query: str, params: Iterable = ()) -> List[dict]:
    with get_connection() as conn:
        cur = conn.execute(query, params)
        return rows_to_dicts(cur.fetchall())


def fetchone(query: str, params: Iterable = ()) -> Optional[dict]:
    with get_connection() as conn:
        cur = conn.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(query: str, params: Iterable = ()) -> None:
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()


def get_setting(key: str, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
    if conn:
        cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None
    else:
        with get_connection() as local_conn:
            cur = local_conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

