"""Grade a model as a player through the curated bank, using the same gate a
human is graded by. Pure and deterministic: the model-call side is injected as a
`decide` callable, so this module has no provider dependency and is fully
testable with a stub."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from blast_radius.engine.grader import classify_oversight_bias, grade_decision
from blast_radius.models import (
    Action,
    BlastRadiusConfig,
    OversightBias,
    PlayerDecision,
    Scenario,
)

# A reasoning string the gate accepts (>= 8 chars) but which names no tell, used
# when a model returns empty/too-short reasoning — it honestly scores 0 coverage.
_EMPTY_REASONING = "no tell named"


@dataclass(frozen=True)
class ModelChoice:
    """What a model player returns — the same two things a human supplies: an
    action and a one-sentence justification (the tell)."""

    action: str
    reasoning: str
    # Optional sandbox policy; when a model chooses sandbox without one, the
    # harness grades against a zero-trust default so the action still scores.
    config: BlastRadiusConfig | None = None


# A model player sees ONLY what a human sees. Ground truth — the correct action,
# the tells, the explanation, receipts, and the safe sandbox policy — is never in
# this view, so the model is graded on the identical evidence a human works from.
def player_view(scenario: Scenario) -> dict:
    presentation = scenario.presentation
    return {
        "family": scenario.family.value,
        "eyebrow": presentation.eyebrow,
        "ask_text": presentation.ask_text,
        "agent_note": presentation.agent_note,
        "artifacts": [
            {"title": artifact.title, "kind": artifact.kind, "content": artifact.content}
            for artifact in presentation.artifacts
        ],
    }


@dataclass
class ScenarioEval:
    scenario_id: str
    family: str
    action: str
    correct_action: str
    action_correct: bool
    reasoning_score: int
    verdict: str

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "family": self.family,
            "action": self.action,
            "correct_action": self.correct_action,
            "action_correct": self.action_correct,
            "reasoning_score": self.reasoning_score,
            "verdict": self.verdict,
        }


@dataclass
class ModelEvalReport:
    model: str
    total: int
    action_correct: int
    action_accuracy: int
    average_tell_coverage: int
    oversight_bias: OversightBias | None
    results: list[ScenarioEval]
    graded_by: str = "deterministic"
    note: str = (
        "The model played the same scenarios a human plays and was graded by the "
        "same deterministic gate. The model never gated anything and never saw the "
        "ground truth — it is scored on the exact evidence a human works from."
    )

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "graded_by": self.graded_by,
            "total": self.total,
            "action_correct": self.action_correct,
            "action_accuracy": self.action_accuracy,
            "average_tell_coverage": self.average_tell_coverage,
            "oversight_bias": (
                self.oversight_bias.model_dump() if self.oversight_bias else None
            ),
            "results": [result.to_dict() for result in self.results],
            "note": self.note,
        }


def _decision(scenario: Scenario, choice: ModelChoice) -> PlayerDecision:
    reasoning = " ".join(choice.reasoning.split())
    if len(reasoning) < 8:
        reasoning = _EMPTY_REASONING
    # Action(...) raises on anything outside approve/sandbox/reject; the caller's
    # structured schema constrains the model, and a stray value is a real failure.
    action = Action(choice.action.strip().lower())
    config = choice.config
    if action is Action.SANDBOX and config is None:
        config = BlastRadiusConfig()
    return PlayerDecision(
        scenario_id=scenario.id,
        action=action,
        reasoning_text=reasoning,
        blast_radius_config=config,
    )


def evaluate_model(
    scenarios: Iterable[Scenario],
    decide: Callable[[dict], ModelChoice],
    *,
    model: str = "model",
) -> ModelEvalReport:
    """Grade `decide` over every scenario. `decide` receives only `player_view`
    (never ground truth) and returns a ModelChoice."""
    results: list[ScenarioEval] = []
    grades = []
    for scenario in scenarios:
        choice = decide(player_view(scenario))
        grade = grade_decision(scenario, _decision(scenario, choice))
        grades.append(grade)
        results.append(
            ScenarioEval(
                scenario_id=scenario.id,
                family=grade.family or scenario.family.value,
                action=grade.action or "",
                correct_action=grade.correct_action or "",
                action_correct=grade.action_correct,
                reasoning_score=grade.reasoning_score,
                verdict=grade.verdict,
            )
        )
    total = len(results)
    action_correct = sum(1 for result in results if result.action_correct)
    average_tell_coverage = (
        round(sum(result.reasoning_score for result in results) / total) if total else 0
    )
    return ModelEvalReport(
        model=model,
        total=total,
        action_correct=action_correct,
        action_accuracy=round(100 * action_correct / total) if total else 0,
        average_tell_coverage=average_tell_coverage,
        oversight_bias=classify_oversight_bias(grades),
        results=results,
    )
