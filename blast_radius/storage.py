from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from blast_radius.models import SessionState


class SessionStore:
    def __init__(self, path: Path, ttl_minutes: int):
        self.path = path
        self.ttl = timedelta(minutes=ttl_minutes)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )

    def save(self, state: SessionState) -> None:
        state.updated_at = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions(id, state_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json, "
                "updated_at=excluded.updated_at",
                (state.id, state.model_dump_json(), state.updated_at.isoformat()),
            )

    def get(self, session_id: str) -> SessionState | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT state_json, updated_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        updated = datetime.fromisoformat(row[1])
        if datetime.now(UTC) - updated > self.ttl:
            self.delete(session_id)
            return None
        return SessionState.model_validate_json(row[0])

    def delete(self, session_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
