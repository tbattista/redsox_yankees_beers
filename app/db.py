from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

# Paid/unpaid state is stored server-side in a single JSON file so it survives
# across seasons (organized by year) and is easy to read or back up by hand.
# Point DATA_DIR at a persistent volume so the file isn't wiped on redeploy.
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
JSON_PATH = DATA_DIR / "payments.json"
_LEGACY_DB_PATH = DATA_DIR / "app.db"

# Read-modify-write of the JSON file is guarded so concurrent toggles don't
# clobber each other.
_LOCK = threading.Lock()


def _load() -> dict:
    """Load the whole store: {season(str): {anchor_game_pk(str): {...}}}."""
    if not JSON_PATH.exists():
        return {}
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    """Atomically write the store (temp file + os.replace) so a crash mid-write
    can't corrupt the JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, JSON_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _migrate_from_sqlite() -> None:
    """One-time import of paid flags from the old SQLite store, if present."""
    if not _LEGACY_DB_PATH.exists():
        return
    try:
        import sqlite3

        conn = sqlite3.connect(_LEGACY_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT season, anchor_game_pk, paid, paid_at FROM series_payments"
        ).fetchall()
        conn.close()
    except Exception:
        return  # no/old/corrupt DB — nothing to migrate

    data: dict = {}
    for r in rows:
        if r["paid"]:
            season_map = data.setdefault(str(r["season"]), {})
            season_map[str(r["anchor_game_pk"])] = {
                "paid": True,
                "paid_at": r["paid_at"],
            }
    if data:
        with _LOCK:
            _save(data)


def init_db() -> None:
    """Ensure the data dir exists and seed from the legacy SQLite DB once."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not JSON_PATH.exists():
        _migrate_from_sqlite()


def get_paid_map(season: int) -> dict[int, dict]:
    """Return {anchor_game_pk: {"paid": bool, "paid_at": str|None}} for a season."""
    with _LOCK:
        data = _load()
    season_map = data.get(str(season), {})
    return {
        int(pk): {"paid": bool(info.get("paid")), "paid_at": info.get("paid_at")}
        for pk, info in season_map.items()
    }


def set_paid(season: int, anchor_game_pk: int, paid: bool) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds") if paid else None
    with _LOCK:
        data = _load()
        season_map = data.setdefault(str(season), {})
        if paid:
            season_map[str(anchor_game_pk)] = {"paid": True, "paid_at": now}
        else:
            # Unpaid is the default, so drop the record to keep the file tidy.
            season_map.pop(str(anchor_game_pk), None)
            if not season_map:
                data.pop(str(season), None)
        _save(data)
