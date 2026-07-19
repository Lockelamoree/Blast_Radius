from __future__ import annotations

import sqlite3
import threading
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from blast_radius.models import (
    PetConfig,
    SessionState,
    SessionSummary,
    level_for_score,
)

# Sentinel so upsert_user can tell "leave this column alone" apart from an
# explicit None (which clears the nickname back to anonymous).
_UNSET: Any = object()


@dataclass(frozen=True)
class UserRecord:
    uid: str
    nickname: str | None
    pet: PetConfig
    created_at: str
    updated_at: str


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
            # Persistent users: a signed per-browser uid, an optional self-chosen
            # nickname, and the JSON-encoded custom pet. Outlives sessions.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "uid TEXT PRIMARY KEY, nickname TEXT, pet_json TEXT, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            self._migrate_summaries(connection)

    def _migrate_summaries(self, connection: sqlite3.Connection) -> None:
        """Add columns the persistent-scoring feature needs to a session_summaries
        table that predates it. CREATE TABLE IF NOT EXISTS never alters an existing
        table, so a prod DB created before this feature keeps the old shape until
        we ALTER it here. Idempotent: guarded by the live column set."""
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(session_summaries)")
        }
        if "user_id" not in columns:
            connection.execute("ALTER TABLE session_summaries ADD COLUMN user_id TEXT")
        if "score" not in columns:
            connection.execute("ALTER TABLE session_summaries ADD COLUMN score INTEGER")

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

    def record_summary(
        self, summary: SessionSummary, user_id: str | None = None
    ) -> None:
        """Persist a scores-only summary once; retries are no-ops (append-only).

        ``user_id`` links the run to a persistent user for the leaderboard. It is
        an opaque per-browser token, never PII, kept alongside (not inside) the
        SessionSummary model so the model's 'no identifiers' contract holds."""
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO session_summaries("
                "session_id, finished_at, mode, operator_handle, pretest, posttest, "
                "delta, rounds_played, rounds_generated, average_reasoning, "
                "families_cleared, weakest, competency_json, finished_early, "
                "user_id, score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
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
                    user_id,
                    summary.score,
                ),
            )

    def list_summaries(self, limit: int = 500) -> list[SessionSummary]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT session_id, finished_at, mode, operator_handle, pretest, "
                "posttest, delta, rounds_played, rounds_generated, average_reasoning, "
                "families_cleared, weakest, competency_json, finished_early, "
                "COALESCE(score, 0) "
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
                score=row[14],
            )
            for row in rows
        ]

    # ---------- persistent users + leaderboard ----------
    def get_user(self, uid: str) -> UserRecord | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT uid, nickname, pet_json, created_at, updated_at "
                "FROM users WHERE uid = ?",
                (uid,),
            ).fetchone()
        if row is None:
            return None
        # A corrupt / stale pet blob must never 500 a profile read; fall back to
        # the default pet so the user simply sees a fresh companion.
        try:
            pet = PetConfig.model_validate_json(row[2]) if row[2] else PetConfig()
        except ValueError:
            pet = PetConfig()
        return UserRecord(
            uid=row[0],
            nickname=row[1],
            pet=pet,
            created_at=row[3],
            updated_at=row[4],
        )

    def upsert_user(
        self,
        uid: str,
        *,
        nickname: Any = _UNSET,
        pet_json: Any = _UNSET,
    ) -> None:
        """Create or partially update a user row. Only the columns whose keyword
        is supplied are written; the sentinel leaves the others untouched."""
        now = datetime.now(UTC).isoformat()
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO users(uid, nickname, pet_json, created_at, updated_at) "
                "VALUES (:uid, :nickname, :pet_json, :created_at, :updated_at) "
                "ON CONFLICT(uid) DO UPDATE SET "
                "nickname=CASE WHEN :set_nick THEN :nickname ELSE users.nickname END, "
                "pet_json=CASE WHEN :set_pet THEN :pet_json ELSE users.pet_json END, "
                "updated_at=:updated_at",
                {
                    "uid": uid,
                    "nickname": None if nickname is _UNSET else nickname,
                    "pet_json": None if pet_json is _UNSET else pet_json,
                    "created_at": now,
                    "updated_at": now,
                    "set_nick": 1 if nickname is not _UNSET else 0,
                    "set_pet": 1 if pet_json is not _UNSET else 0,
                },
            )

    def leaderboard(self, limit: int = 100) -> list[dict]:
        """Rank persistent users by cumulative score. Legacy rows with no user_id
        (recorded before identity existed) are excluded so the board stays clean."""
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT s.user_id, COALESCE(u.nickname, '') AS nickname, "
                "SUM(COALESCE(s.score, 0)) AS total_score, COUNT(*) AS sessions, "
                "MAX(s.delta) AS best_delta, MAX(s.families_cleared) AS families_cleared "
                "FROM session_summaries s LEFT JOIN users u ON u.uid = s.user_id "
                "WHERE s.user_id IS NOT NULL "
                "GROUP BY s.user_id "
                "ORDER BY total_score DESC, sessions DESC, s.user_id ASC "
                "LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [
            {
                "user_id": row[0],
                "nickname": row[1],
                "score": int(row[2] or 0),
                "sessions": int(row[3] or 0),
                "best_delta": row[4],
                "families_cleared": int(row[5] or 0),
                "level": level_for_score(int(row[2] or 0)),
            }
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
