from __future__ import annotations

from blast_radius.config import Settings
from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.gate import CorrectnessGate
from blast_radius.engine.grader import grade_decision
from blast_radius.engine.openai_adapter import OpenAIAdapter
from blast_radius.models import GradeResult, PlayerDecision, Scenario, ScenarioFamily


class TrustEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bank = ScenarioBank(settings.data_dir)
        self.gate = CorrectnessGate(self.bank)
        self.openai = OpenAIAdapter(settings)

    async def next_scenario(
        self,
        *,
        family: ScenarioFamily | None,
        difficulty: int,
        blind_spot: str,
        competency: dict[str, dict[str, int]],
        exclude: set[str],
        seed: str,
    ) -> tuple[Scenario, str | None]:
        failure_reason: str | None = None
        if self.openai.enabled and family is not None:
            template = next(
                (row for row in self.bank.templates.values() if row["family"] == family.value),
                None,
            )
            if template:
                blind_spot = await self.openai.adapt_blind_spot(competency, blind_spot)
                generated = await self.openai.generate(template, difficulty, blind_spot)
                if generated:
                    result = self.gate.verify(generated)
                    if result.passed:
                        critic = await self.openai.critic_gate(generated, template)
                        if critic and critic.passed:
                            return generated, None
                        failure_reason = (
                            "; ".join(critic.reasons)
                            if critic
                            else "critic correctness gate unavailable"
                        )
                    else:
                        failure_reason = "; ".join(result.reasons)
                else:
                    failure_reason = "live generation unavailable"
        fallback = self.bank.fallback(family=family, exclude=exclude, seed=seed)
        result = self.gate.verify(fallback)
        if not result.passed:
            raise RuntimeError(f"verified fallback failed gate: {result.reasons}")
        return fallback, failure_reason

    async def grade(self, scenario: Scenario, decision: PlayerDecision) -> GradeResult:
        grade = grade_decision(scenario, decision)
        if not self.openai.enabled:
            return grade
        review = await self.openai.critique_reasoning(scenario, decision)
        if review is None:
            return grade
        allowed = set(scenario.ground_truth.tells)
        matched = list(dict.fromkeys(tell for tell in review.matched_tells if tell in allowed))
        grade.matched_tells = matched
        grade.missed_tells = [tell for tell in scenario.ground_truth.tells if tell not in matched]
        grade.reasoning_score = round(100 * len(matched) / len(scenario.ground_truth.tells))
        grade.socratic_followup = review.followup
        if grade.action_correct and grade.reasoning_score >= 60 and (
            grade.blast_radius_score is None or grade.blast_radius_score >= 70
        ):
            grade.verdict = "correct"
        elif grade.action_correct or grade.reasoning_score >= 50:
            grade.verdict = "partial"
        else:
            grade.verdict = "wrong"
        return grade
