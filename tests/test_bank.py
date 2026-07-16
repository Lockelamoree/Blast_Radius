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
