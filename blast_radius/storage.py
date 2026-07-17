from __future__ import annotations

import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

from blast_radius.models import SessionState, SessionSummary


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

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as connection, connection:
            yield connection

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS llm_daily_usage ("
                "usage_day TEXT PRIMARY KEY, calls INTEGER NOT NULL)"
            )
            # Scores-only summaries of finished sessions. Append-only and
            # deliberately outside the session TTL so the team board can
            # aggregate runs after their session rows expire.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS session_summaries ("
                "session_id TEXT PRIMARY KEY, finished_at TEXT NOT NULL, "
                "mode TEXT NOT NULL, operator_handle TEXT, "
                "pretest INTEGER NOT NULL, posttest INTEGER, delta INTEGER, "
                "rounds_played INTEGER NOT NULL, rounds_generated INTEGER NOT NULL, "
                "average_reasoning INTEGER NOT NULL, families_cleared INTEGER NOT NULL, "
                "weakest TEXT, competency_json TEXT NOT NULL, "
                "finished_early INTEGER NOT NULL)"
            )

    def save(self, state: SessionState) -> None:
        state.updated_at = datetime.now(UTC)
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO sessions(id, state_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json, "
                "updated_at=excluded.updated_at",
                (state.id, state.model_dump_json(), state.updated_at.isoformat()),
            )

    def get(self, session_id: str) -> SessionState | None:
        with self._lock, self._connection() as connection:
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
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def record_summary(self, summary: SessionSummary) -> None:
        """Persist a scores-only summary once; retries are no-ops (append-only)."""
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO session_summaries("
                "session_id, finished_at, mode, operator_handle, pretest, posttest, "
                "delta, rounds_played, rounds_generated, average_reasoning, "
                "families_cleared, weakest, competency_json, finished_early) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO NOTHING",
                (
                    summary.session_id,
                    summary.finished_at.isoformat(),
                    summary.mode,
                    summary.operator_handle,
                    summary.pretest,
                    summary.posttest,
                    summary.delta,
                    summary.rounds_played,
                    summary.rounds_generated,
                    summary.average_reasoning,
                    summary.families_cleared,
                    summary.weakest,
                    summary.competency_json,
                    int(summary.finished_early),
                ),
            )

    def list_summaries(self, limit: int = 500) -> list[SessionSummary]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT session_id, finished_at, mode, operator_handle, pretest, "
                "posttest, delta, rounds_played, rounds_generated, average_reasoning, "
                "families_cleared, weakest, competency_json, finished_early "
                "FROM session_summaries ORDER BY finished_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [
            SessionSummary(
                session_id=row[0],
                finished_at=datetime.fromisoformat(row[1]),
                mode=row[2],
                operator_handle=row[3],
                pretest=row[4],
                posttest=row[5],
                delta=row[6],
                rounds_played=row[7],
                rounds_generated=row[8],
                average_reasoning=row[9],
                families_cleared=row[10],
                weakest=row[11],
                competency_json=row[12],
                finished_early=bool(row[13]),
            )
            for row in rows
        ]

    def reserve_llm_call(self, daily_limit: int, now: datetime | None = None) -> str | None:
        """Atomically reserve one call and return its UTC usage day."""
        if daily_limit <= 0:
            return None
        usage_day = (now or datetime.now(UTC)).date().isoformat()
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT calls FROM llm_daily_usage WHERE usage_day = ?", (usage_day,)
            ).fetchone()
            calls = int(row[0]) if row else 0
            if calls >= daily_limit:
                return None
            connection.execute(
                "INSERT INTO llm_daily_usage(usage_day, calls) VALUES (?, 1) "
                "ON CONFLICT(usage_day) DO UPDATE SET calls=calls + 1",
                (usage_day,),
            )
        return usage_day

    def refund_llm_call(self, usage_day: str) -> None:
        """Release a failed structured call without allowing the count below zero."""
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE llm_daily_usage SET calls = calls - 1 "
                "WHERE usage_day = ? AND calls > 0",
                (usage_day,),
            )
            connection.execute(
                "DELETE FROM llm_daily_usage WHERE usage_day = ? AND calls <= 0",
                (usage_day,),
            )

    def llm_usage(self, now: datetime | None = None) -> int:
        usage_day = (now or datetime.now(UTC)).date().isoformat()
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT calls FROM llm_daily_usage WHERE usage_day = ?", (usage_day,)
            ).fetchone()
        return int(row[0]) if row else 0

    def budget_remaining(self, daily_limit: int, now: datetime | None = None) -> int:
        """Return remaining UTC-day capacity without reserving a call."""
        return max(0, daily_limit - self.llm_usage(now))

    def try_consume_llm_call(self, daily_limit: int, now: datetime | None = None) -> bool:
        """Backward-compatible reservation helper."""
        return self.reserve_llm_call(daily_limit, now) is not None
