"""
bean/memory/store.py

The memory store. SQLite-backed. WAL mode. Boring on purpose.
This is the only thing allowed to touch the database file directly.
Everything else goes through this module.
"""

import sqlite3
import os
import threading
from pathlib import Path
from typing import Optional


_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "memory_schema.sql"

# Thread-local storage for connections (SQLite connections are not thread-safe)
_local = threading.local()


class MemoryStore:
    """
    Manages the BEAN SQLite memory database.
    
    One instance per process. Thread-safe via thread-local connections.
    WAL mode enabled for concurrent reads during writes.
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self):
        """Apply schema if not already applied. Idempotent."""
        schema = _SCHEMA_PATH.read_text()
        conn = self._conn()
        conn.executescript(schema)
        conn.commit()

    def _conn(self) -> sqlite3.Connection:
        """Return a thread-local connection, creating if needed."""
        if not hasattr(_local, "conn") or _local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            _local.conn = conn
        return _local.conn

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        return self._conn().execute(sql, params)

    def executemany(self, sql: str, params_list) -> sqlite3.Cursor:
        return self._conn().executemany(sql, params_list)

    def commit(self):
        self._conn().commit()

    def fetchone(self, sql: str, params=()) -> Optional[sqlite3.Row]:
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params=()) -> list:
        return self.execute(sql, params).fetchall()

    def close(self):
        if hasattr(_local, "conn") and _local.conn:
            _local.conn.close()
            _local.conn = None


# Module-level singleton — initialized by runtime bootstrap
_store: Optional[MemoryStore] = None


def init_store(db_path: str) -> MemoryStore:
    global _store
    _store = MemoryStore(db_path)
    return _store


def get_store() -> MemoryStore:
    if _store is None:
        raise RuntimeError(
            "MemoryStore not initialized. Call init_store() first."
        )
    return _store
