from __future__ import annotations

import re
from collections import Counter

from blast_radius.engine.bank import ScenarioBank
from blast_radius.models import Action, GateResult, Scenario


class CorrectnessGate:
    """Deterministic invariant gate. It never executes an artifact."""

    def __init__(self, bank: ScenarioBank):
        self.bank = bank

    @staticmethod
    def _compare_trusted_fields(
        scenario: Scenario,
        trusted_base: Scenario,
        *,
        require_difficulty: bool,
    ) -> list[str]:
        reasons: list[str] = []
        if scenario.family != trusted_base.family:
            reasons.append("scenario family differs from trusted base")
        if scenario.template_ref != trusted_base.template_ref:
            reasons.append("scenario template differs from trusted base")
        if require_difficulty and scenario.difficulty != trusted_base.difficulty:
            reasons.append("curated scenario difficulty was modified")
        if scenario.ground_truth != trusted_base.ground_truth:
            reasons.append("scenario ground truth differs from trusted base")
        return reasons

    @staticmethod
    def _compare_generated_presentation(
        scenario: Scenario,
        trusted_base: Scenario,
    ) -> list[str]:
        reasons: list[str] = []
        candidate = scenario.presentation
        trusted = trusted_base.presentation
        if (
            candidate.eyebrow != trusted.eyebrow
            or candidate.ask_text != trusted.ask_text
            or candidate.agent_note != trusted.agent_note
        ):
            reasons.append("generated presentation identity differs from trusted base")
        if len(candidate.artifacts) != len(trusted.artifacts):
            reasons.append("generated artifact count differs from trusted base")
            return reasons
        candidate_artifacts = Counter(
            artifact.model_dump_json() for artifact in candidate.artifacts
        )
        trusted_artifacts = Counter(
            artifact.model_dump_json() for artifact in trusted.artifacts
        )
        if candidate_artifacts != trusted_artifacts:
            reasons.append("generated artifacts differ from the curated evidence set")
        return reasons

    @staticmethod
    def _contains_keyword(content: str, keyword: str) -> bool:
        keyword = keyword.lower()
        suffix = r"(?:s|es)?" if keyword.isalpha() and len(keyword) >= 4 else ""
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}{suffix}(?![a-z0-9])"
        normalized_content = re.sub(r"[_-]+", " ", content)
        return bool(re.search(pattern, content) or re.search(pattern, normalized_content))

    def verify(
        self, scenario: Scenario, trusted_base: Scenario | None = None
    ) -> GateResult:
        reasons: list[str] = []
        if trusted_base is not None:
            curated_base = self.bank.scenarios.get(trusted_base.id)
            if curated_base is None:
                reasons.append("trusted base is not in the curated bank")
            elif trusted_base != curated_base:
                reasons.append("trusted base was modified from the curated bank")
            if curated_base is not None:
                reasons.extend(
                    self._compare_trusted_fields(
                        scenario, curated_base, require_difficulty=False
                    )
                )
                reasons.extend(
                    self._compare_generated_presentation(scenario, curated_base)
                )
        elif curated_scenario := self.bank.scenarios.get(scenario.id):
            reasons.extend(
                self._compare_trusted_fields(
                    scenario, curated_scenario, require_difficulty=True
                )
            )
            if scenario.presentation != curated_scenario.presentation:
                reasons.append("curated scenario presentation was modified")

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
        if any(
            not keyword.strip()
            for keywords in truth.tell_keywords.values()
            for keyword in keywords
        ):
            reasons.append("tell keywords cannot be blank")
        if len({evidence.id for evidence in truth.evidence}) != len(truth.evidence):
            reasons.append("evidence identifiers must be unique")
        if truth.correct_action == Action.SANDBOX and truth.safe_blast_radius is None:
            reasons.append("sandbox action has no safe policy")
        if truth.correct_action != Action.SANDBOX and truth.safe_blast_radius is not None:
            reasons.append("non-sandbox action defines a contradictory safe policy")
        if not truth.explanation.strip():
            reasons.append("missing explanation")

        combined_artifacts = "\n".join(
            artifact.content.lower() for artifact in scenario.presentation.artifacts
        )
        for tell, keywords in truth.tell_keywords.items():
            usable_keywords = [keyword for keyword in keywords if keyword.strip()]
            if not any(
                self._contains_keyword(combined_artifacts, keyword)
                for keyword in usable_keywords
            ):
                reasons.append(f"presented artifacts do not support declared tell: {tell}")

        return GateResult(
            passed=not reasons,
            reasons=reasons,
            scenario_id=scenario.id,
        )
