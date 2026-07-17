from pathlib import Path

from blast_radius.engine.bank import ScenarioBank
from blast_radius.eval import ModelChoice, evaluate_model, player_view

DATA_DIR = Path(__file__).resolve().parents[1] / "blast_radius" / "data"


def _bank() -> ScenarioBank:
    return ScenarioBank(DATA_DIR)


def test_player_view_never_exposes_ground_truth() -> None:
    # A model player must be graded on the same evidence a human sees. Ground
    # truth (the correct action, the tells, the explanation, the receipts) must
    # never leak into the view — including via the scenario id.
    bank = _bank()
    for scenario in bank.scenarios.values():
        view = player_view(scenario)
        keys = set(view)
        assert not keys & {
            "id",
            "correct_action",
            "tells",
            "tell_keywords",
            "explanation",
            "evidence",
            "receipts",
            "safe_blast_radius",
            "ground_truth",
        }
        blob = str(view).lower()
        assert scenario.ground_truth.correct_action.value not in view.get("family", "x")
        # The id (e.g. "cmd-exfil-1") telegraphs the answer, so it stays out.
        assert scenario.id not in blob


def test_evaluate_model_grades_every_scenario_by_the_same_gate() -> None:
    bank = _bank()
    scenarios = list(bank.scenarios.values())

    # A dumb player that always rejects with a generic justification.
    def always_reject(_view: dict) -> ModelChoice:
        return ModelChoice(action="reject", reasoning="this action looks dangerous")

    report = evaluate_model(scenarios, always_reject, model="stub")
    assert report.total == len(scenarios)
    assert report.model == "stub"
    assert report.graded_by == "deterministic"
    assert 0 <= report.action_accuracy <= 100
    assert 0 <= report.average_tell_coverage <= 100
    assert len(report.results) == len(scenarios)
    for result in report.results:
        assert result.correct_action in {"approve", "sandbox", "reject"}
        assert result.action == "reject"
    # Always-reject can only be wrong by over-restriction, never over-approval.
    assert report.oversight_bias is not None
    assert report.oversight_bias.over_approval == 0


def test_a_perfect_action_player_scores_full_action_accuracy() -> None:
    # The test may peek at ground truth to build a perfect player; the harness and
    # the model under test may not. Keyed on ask_text (never exposed correct action).
    bank = _bank()
    scenarios = list(bank.scenarios.values())
    answers = {
        s.presentation.ask_text: s.ground_truth.correct_action.value for s in scenarios
    }
    assert len(answers) == len(scenarios), "ask_text must be unique to key the oracle"

    def perfect(view: dict) -> ModelChoice:
        return ModelChoice(action=answers[view["ask_text"]], reasoning="named the tell")

    report = evaluate_model(scenarios, perfect, model="oracle")
    assert report.action_correct == len(scenarios)
    assert report.action_accuracy == 100
    assert report.oversight_bias is not None
    assert report.oversight_bias.dominant == "none"


def test_short_reasoning_is_accepted_and_scores_zero_coverage() -> None:
    bank = _bank()
    scenario = next(iter(bank.scenarios.values()))

    def terse(_view: dict) -> ModelChoice:
        return ModelChoice(action="reject", reasoning="")

    report = evaluate_model([scenario], terse, model="terse")
    assert report.total == 1
    assert report.results[0].reasoning_score == 0
