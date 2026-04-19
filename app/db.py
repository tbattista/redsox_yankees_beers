from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
DB_PATH = DATA_DIR / "app.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _cursor() -> Iterator[sqlite3.Cursor]:
    conn = _connect()
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS series_payments (
                season INTEGER NOT NULL,
                anchor_game_pk INTEGER NOT NULL,
                paid INTEGER NOT NULL DEFAULT 0,
                paid_at TEXT,
                PRIMARY KEY (season, anchor_game_pk)
            )
            """
        )


def get_paid_map(season: int) -> dict[int, dict]:
    """Return {anchor_game_pk: {"paid": bool, "paid_at": str|None}}."""
    with _cursor() as cur:
        cur.execute(
            "SELECT anchor_game_pk, paid, paid_at FROM series_payments WHERE season = ?",
            (season,),
        )
        return {
            row["anchor_game_pk"]: {"paid": bool(row["paid"]), "paid_at": row["paid_at"]}
            for row in cur.fetchall()
        }


def set_paid(season: int, anchor_game_pk: int, paid: bool) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds") if paid else None
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO series_payments (season, anchor_game_pk, paid, paid_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(season, anchor_game_pk) DO UPDATE SET
                paid = excluded.paid,
                paid_at = excluded.paid_at
            """,
            (season, anchor_game_pk, 1 if paid else 0, now),
        )
