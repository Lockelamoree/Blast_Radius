import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from blast_radius.models import PetConfig, SessionSummary
from blast_radius.storage import SessionStore


def _summary(session_id: str, score: int, **overrides) -> SessionSummary:
    base = dict(
        session_id=session_id,
        finished_at=datetime(2026, 7, 17, 12, tzinfo=UTC),
        mode="demo",
        pretest=3,
        posttest=5,
        delta=2,
        rounds_played=6,
        rounds_generated=0,
        average_reasoning=70,
        families_cleared=4,
        weakest="provenance",
        competency_json="{}",
        finished_early=False,
        score=score,
    )
    base.update(overrides)
    return SessionSummary(**base)


def test_daily_llm_budget_is_atomic_and_resets_by_utc_day(tmp_path) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    today = datetime(2026, 7, 14, 12, tzinfo=UTC)

    assert store.try_consume_llm_call(2, now=today)
    assert store.budget_remaining(2, now=today) == 1
    assert store.try_consume_llm_call(2, now=today)
    assert store.budget_remaining(2, now=today) == 0
    assert not store.try_consume_llm_call(2, now=today)
    assert store.try_consume_llm_call(2, now=today + timedelta(days=1))


def test_zero_daily_budget_disables_model_calls(tmp_path) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    assert not store.try_consume_llm_call(0)


def test_budget_reservations_are_concurrent_and_refundable(tmp_path) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)

    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: store.reserve_llm_call(3), range(12)))

    granted = [reservation for reservation in reservations if reservation is not None]
    assert len(granted) == 3
    assert store.llm_usage() == 3

    store.refund_llm_call(granted[0])
    assert store.llm_usage() == 2
    assert store.reserve_llm_call(3) is not None
    assert store.llm_usage() == 3


def test_store_closes_each_operation_connection(tmp_path, monkeypatch) -> None:
    store = SessionStore(tmp_path / "connections.db", ttl_minutes=180)
    real_connect = store._connect
    closed: list[bool] = []

    class TrackingConnection:
        def __init__(self):
            self.connection = real_connect()

        def __enter__(self):
            return self.connection.__enter__()

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def close(self) -> None:
            self.connection.close()
            closed.append(True)

    monkeypatch.setattr(store, "_connect", TrackingConnection)

    for _ in range(40):
        assert store.llm_usage() == 0
    assert closed == [True] * 40


def test_session_summaries_are_append_only_and_survive_session_expiry(tmp_path) -> None:
    from blast_radius.models import SessionSummary

    store = SessionStore(tmp_path / "summaries.db", ttl_minutes=180)
    summary = SessionSummary(
        session_id="sess-1",
        finished_at=datetime(2026, 7, 17, 12, tzinfo=UTC),
        mode="demo",
        operator_handle="max-g",
        pretest=3,
        posttest=5,
        delta=2,
        rounds_played=6,
        rounds_generated=1,
        average_reasoning=74,
        families_cleared=5,
        weakest="provenance",
        competency_json="{}",
        finished_early=False,
    )
    store.record_summary(summary)
    # Idempotent under client retries: a second write with different scores
    # must NOT overwrite the first (append-only).
    store.record_summary(summary.model_copy(update={"delta": -5}))
    rows = store.list_summaries()
    assert len(rows) == 1
    assert rows[0].delta == 2
    assert rows[0].operator_handle == "max-g"

    # Deleting the session row does not touch the durable summary.
    store.delete("sess-1")
    assert len(store.list_summaries()) == 1

    # A fresh store over the same file still sees it (persists across boots).
    reopened = SessionStore(tmp_path / "summaries.db", ttl_minutes=180)
    assert reopened.list_summaries()[0].session_id == "sess-1"


def test_session_summaries_preserve_null_delta_for_early_finishes(tmp_path) -> None:
    from blast_radius.models import SessionSummary

    store = SessionStore(tmp_path / "early.db", ttl_minutes=180)
    store.record_summary(
        SessionSummary(
            session_id="sess-early",
            finished_at=datetime(2026, 7, 17, 13, tzinfo=UTC),
            mode="live",
            pretest=4,
            rounds_played=2,
            rounds_generated=0,
            average_reasoning=50,
            families_cleared=1,
            competency_json="{}",
            finished_early=True,
        )
    )
    row = store.list_summaries()[0]
    assert row.posttest is None
    assert row.delta is None
    assert row.finished_early is True
    assert row.operator_handle is None


def _old_schema_db(path) -> None:
    """Create a session_summaries table in the shape it had before persistent
    scoring existed (no user_id / score), with one legacy row."""
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE session_summaries ("
        "session_id TEXT PRIMARY KEY, finished_at TEXT NOT NULL, mode TEXT NOT NULL, "
        "operator_handle TEXT, pretest INTEGER NOT NULL, posttest INTEGER, delta INTEGER, "
        "rounds_played INTEGER NOT NULL, rounds_generated INTEGER NOT NULL, "
        "average_reasoning INTEGER NOT NULL, families_cleared INTEGER NOT NULL, "
        "weakest TEXT, competency_json TEXT NOT NULL, finished_early INTEGER NOT NULL)"
    )
    connection.execute(
        "INSERT INTO session_summaries VALUES "
        "('legacy-1','2026-07-10T12:00:00+00:00','demo','oldtimer',2,4,2,5,0,60,3,'scope','{}',0)"
    )
    connection.commit()
    connection.close()


def test_summary_migration_adds_columns_and_is_idempotent(tmp_path) -> None:
    db = tmp_path / "legacy.db"
    _old_schema_db(db)

    # First open migrates the table; a second open must be a no-op (not error).
    store = SessionStore(db, ttl_minutes=180)
    SessionStore(db, ttl_minutes=180)

    columns = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(session_summaries)")}
    assert {"user_id", "score"} <= columns
    tables = {row[0] for row in sqlite3.connect(db).execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "users" in tables

    # The legacy row still parses; its missing score coalesces to 0 and, having no
    # user_id, it is excluded from the leaderboard.
    legacy = store.list_summaries()[0]
    assert legacy.session_id == "legacy-1"
    assert legacy.score == 0
    assert store.leaderboard() == []


def test_upsert_user_partial_updates_and_pet_round_trip(tmp_path) -> None:
    store = SessionStore(tmp_path / "users.db", ttl_minutes=180)
    assert store.get_user("uid:a") is None

    store.upsert_user("uid:a", nickname="max-g")
    record = store.get_user("uid:a")
    assert record.nickname == "max-g"
    assert record.pet == PetConfig()  # default until customised

    pet = PetConfig(shape="droplet", palette="violet", face="visor", accessory="halo", trait="playful", name="Sir Byte!!")
    store.upsert_user("uid:a", pet_json=pet.model_dump_json())
    record = store.get_user("uid:a")
    # Updating the pet must not clobber the nickname (partial update).
    assert record.nickname == "max-g"
    assert record.pet.shape == "droplet"
    assert record.pet.palette == "violet"
    assert record.pet.name == "sir_byte"  # slugified

    # A corrupt pet blob degrades to the default rather than raising.
    store.upsert_user("uid:a", pet_json="{not valid json")
    assert store.get_user("uid:a").pet == PetConfig()


def test_leaderboard_aggregates_by_user_and_ranks_by_cumulative_score(tmp_path) -> None:
    store = SessionStore(tmp_path / "board.db", ttl_minutes=180)
    store.upsert_user("uid:a", nickname="max-g")
    store.upsert_user("uid:b", nickname="riley")
    # uid:a plays twice (18 + 30 = 48); uid:b once (40). Anonymous row is excluded.
    store.record_summary(_summary("s1", 18, delta=2), user_id="uid:a")
    store.record_summary(_summary("s2", 30, delta=4, families_cleared=6), user_id="uid:a")
    store.record_summary(_summary("s3", 40, delta=3), user_id="uid:b")
    store.record_summary(_summary("s4", 99), user_id=None)  # legacy / anonymous

    board = store.leaderboard()
    assert [row["user_id"] for row in board] == ["uid:a", "uid:b"]
    top = board[0]
    assert top["nickname"] == "max-g"
    assert top["score"] == 48
    assert top["sessions"] == 2
    assert top["families_cleared"] == 6  # MAX across the user's runs
    assert top["level"] == 2  # floor(sqrt(48/25)) + 1
    assert board[1]["score"] == 40
