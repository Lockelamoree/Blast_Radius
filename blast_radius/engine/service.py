from __future__ import annotations

import logging
from collections.abc import Callable

from blast_radius.config import Settings
from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.gate import CorrectnessGate
from blast_radius.engine.grader import grade_decision, merge_reasoning
from blast_radius.engine.openai_adapter import OpenAIAdapter
from blast_radius.models import GradeResult, PlayerDecision, Scenario, ScenarioFamily

logger = logging.getLogger(__name__)


class TrustEngine:
    def __init__(self, settings: Settings, allow_llm_call: Callable[[], bool] | None = None):
        self.settings = settings
        self.bank = ScenarioBank(settings.data_dir)
        self.gate = CorrectnessGate(self.bank)
        self.openai = OpenAIAdapter(settings, allow_llm_call=allow_llm_call)

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
        if self.openai.generation_enabled and family is not None:
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
        if not self.openai.grading_enabled:
            return grade
        try:
            review = await self.openai.critique_reasoning(scenario, decision)
        except Exception as exc:
            logger.warning("OpenAI reasoning critique failed (%s)", type(exc).__name__)
            return grade
        if review is None:
            return grade
        grade = merge_reasoning(grade, scenario, review.matched_tells, review.followup)
        grade.graded_by = self.settings.critic_model
        return grade
