from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from blast_radius.storage import SessionStore


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
