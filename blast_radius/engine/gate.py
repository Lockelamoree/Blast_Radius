from __future__ import annotations

from blast_radius.engine.bank import ScenarioBank
from blast_radius.models import Action, GateResult, Scenario


class CorrectnessGate:
    """Deterministic invariant gate. It never executes an artifact."""

    def __init__(self, bank: ScenarioBank):
        self.bank = bank

    def verify(self, scenario: Scenario) -> GateResult:
        reasons: list[str] = []
        template = self.bank.templates.get(scenario.template_ref)
        if template is None:
            reasons.append("unknown template_ref")
        elif template["family"] != scenario.family.value:
            reasons.append("template family mismatch")

        truth = scenario.ground_truth
        if set(truth.tells) != set(truth.tell_keywords):
            reasons.append("every tell must have keyword evidence")
        if any(not keywords for keywords in truth.tell_keywords.values()):
            reasons.append("tell keyword groups cannot be empty")
        if len({evidence.id for evidence in truth.evidence}) != len(truth.evidence):
            reasons.append("evidence identifiers must be unique")
        if truth.correct_action == Action.SANDBOX and truth.safe_blast_radius is None:
            reasons.append("sandbox action has no safe policy")
        if not truth.explanation.strip():
            reasons.append("missing explanation")

        combined_artifacts = "\n".join(
            artifact.content.lower() for artifact in scenario.presentation.artifacts
        )
        supported_groups = 0
        for keywords in truth.tell_keywords.values():
            if any(keyword.lower() in combined_artifacts for keyword in keywords):
                supported_groups += 1
        if supported_groups == 0:
            reasons.append("presented artifacts do not support any declared tell")

        return GateResult(
            passed=not reasons,
            reasons=reasons,
            scenario_id=scenario.id,
        )

