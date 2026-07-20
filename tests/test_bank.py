import json
import shutil

import pytest

from blast_radius.engine.bank import ScenarioBank
from blast_radius.models import AssessmentForm, Competency, ScenarioFamily


def test_bank_has_full_requested_coverage(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    assert len(bank.scenarios) >= 18
    assert {scenario.family for scenario in bank.scenarios.values()} == set(ScenarioFamily)
    assert len(bank.questions) == 10
    for form in AssessmentForm:
        questions = bank.questions_for(form)
        assert len(questions) == 5
        assert {question.competency for question in questions} == set(Competency)
    assert {
        question.prompt for question in bank.questions_for(AssessmentForm.PRE)
    }.isdisjoint(
        question.prompt for question in bank.questions_for(AssessmentForm.POST)
    )


def test_public_view_never_contains_ground_truth(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    for scenario in bank.scenarios.values():
        payload = scenario.public_view()
        assert "ground_truth" not in payload
        assert "correct_action" not in str(payload)


def test_seeded_demo_deck_covers_every_family_once_and_is_stable(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    canonical = bank.demo_order()
    # No seed keeps the canonical curated deck for tests and as the fallback.
    assert bank.demo_order(seed=None) == canonical
    families_in_order = [bank.get(scenario_id).family for scenario_id in canonical]

    deck = bank.demo_order(seed="session-a")
    # A session's deck is deterministic and covers the same families in order.
    assert bank.demo_order(seed="session-a") == deck
    assert [bank.get(scenario_id).family for scenario_id in deck] == families_in_order
    assert len(deck) == len(set(deck)) == len(ScenarioFamily)
    assert all(scenario_id in bank.scenarios for scenario_id in deck)


def test_seeded_demo_decks_differ_across_sessions(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    decks = {tuple(bank.demo_order(seed=f"session-{index}")) for index in range(80)}
    # With 3-4 members per family across 6 families there are hundreds of possible
    # decks; a sample of 80 seeds must surface more than one so a replay is not identical.
    assert len(decks) > 1


def write_question_fixture(tmp_path, data_dir, mutate):
    fixture_dir = tmp_path / "data"
    shutil.copytree(data_dir, fixture_dir)
    path = fixture_dir / "questions.json"
    questions = json.loads(path.read_text(encoding="utf-8"))
    mutate(questions)
    path.write_text(json.dumps(questions), encoding="utf-8")
    return fixture_dir


def test_bank_rejects_missing_assessment_competency(test_settings, tmp_path) -> None:
    data_dir = write_question_fixture(
        tmp_path,
        test_settings.data_dir,
        lambda questions: questions.pop(),
    )

    with pytest.raises(ValueError, match="post assessment"):
        ScenarioBank(data_dir)


def test_bank_rejects_duplicate_question_ids(test_settings, tmp_path) -> None:
    def duplicate_id(questions):
        questions[-1]["id"] = questions[0]["id"]

    data_dir = write_question_fixture(tmp_path, test_settings.data_dir, duplicate_id)

    with pytest.raises(ValueError, match="question ids must be unique"):
        ScenarioBank(data_dir)


def test_bank_rejects_duplicate_form_competency(test_settings, tmp_path) -> None:
    def duplicate_competency(questions):
        questions[-1]["competency"] = questions[-2]["competency"]

    data_dir = write_question_fixture(
        tmp_path,
        test_settings.data_dir,
        duplicate_competency,
    )

    with pytest.raises(ValueError, match="post assessment"):
        ScenarioBank(data_dir)


def test_drill_pick_is_deterministic_and_respects_family(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    first = bank.drill_pick(day="2026-07-18", client_key="client-abc")
    again = bank.drill_pick(day="2026-07-18", client_key="client-abc")
    assert first.id == again.id  # same day + client -> same scenario
    next_day = bank.drill_pick(day="2026-07-19", client_key="client-abc")
    # A different day usually rotates the scenario (not asserted strictly to
    # avoid a 1/18 coincidence), but must still be a valid bank scenario.
    assert next_day.id in bank.scenarios

    pinned = bank.drill_pick(
        day="2026-07-18", client_key="client-abc", family=ScenarioFamily.POISONED_DEPENDENCY
    )
    assert pinned.family == ScenarioFamily.POISONED_DEPENDENCY


def test_drill_pick_excludes_recent_ids(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    first = bank.drill_pick(day="2026-07-18", client_key="client-abc")
    # A replay that reports the just-served incident rotates onto a different one,
    # so a judge replaying the drill does not see the same scenario twice in a row.
    replay = bank.drill_pick(day="2026-07-18", client_key="client-abc", exclude={first.id})
    assert replay.id != first.id
    assert replay.id in bank.scenarios
    # Excluding every scenario must not raise — the full set is restored (cycles).
    restored = bank.drill_pick(
        day="2026-07-18", client_key="client-abc", exclude=set(bank.scenarios)
    )
    assert restored.id in bank.scenarios


def test_demo_order_exclude_rotates_member_but_keeps_family_coverage(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    deck = bank.demo_order(seed="session-a")
    excluded = deck[0]  # a dangerous_command member; that family has 3 members
    rotated = bank.demo_order(seed="session-a", exclude={excluded})
    # Still one scenario per family, in the same canonical family order...
    assert [bank.get(s).family for s in rotated] == [bank.get(s).family for s in deck]
    assert len(rotated) == len(set(rotated)) == len(ScenarioFamily)
    # ...but the just-seen member is rotated out.
    assert rotated[0] != excluded
    # Excluding an entire family's pool still represents that family (fallback).
    family = bank.get(deck[1]).family
    members = {sid for sid, sc in bank.scenarios.items() if sc.family == family}
    covered = bank.demo_order(seed="session-a", exclude=members)
    assert bank.get(covered[1]).family == family
