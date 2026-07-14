from datetime import UTC, datetime, timedelta

from blast_radius.storage import SessionStore


def test_daily_llm_budget_is_atomic_and_resets_by_utc_day(tmp_path) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    today = datetime(2026, 7, 14, 12, tzinfo=UTC)

    assert store.try_consume_llm_call(2, now=today)
    assert store.try_consume_llm_call(2, now=today)
    assert not store.try_consume_llm_call(2, now=today)
    assert store.try_consume_llm_call(2, now=today + timedelta(days=1))


def test_zero_daily_budget_disables_model_calls(tmp_path) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    assert not store.try_consume_llm_call(0)
