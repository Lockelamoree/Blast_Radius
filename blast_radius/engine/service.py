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
    def __init__(
        self,
        settings: Settings,
        reserve_llm_call: Callable[[], str | None] | None = None,
        refund_llm_call: Callable[[str], None] | None = None,
    ):
        self.settings = settings
        self.bank = ScenarioBank(settings.data_dir)
        self.gate = CorrectnessGate(self.bank)
        self.openai = OpenAIAdapter(
            settings,
            reserve_llm_call=reserve_llm_call,
            refund_llm_call=refund_llm_call,
        )

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
                        critic_result = await self.openai.critic_gate(generated, template)
                        critic = critic_result.value if critic_result else None
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
        deterministic_matched_tells = list(grade.matched_tells)
        if not self.openai.grading_enabled:
            return grade
        try:
            review = await self.openai.critique_reasoning(scenario, decision)
        except Exception as exc:
            logger.warning("OpenAI reasoning critique failed (%s)", type(exc).__name__)
            return grade
        if review is None:
            return grade
        allowed = set(scenario.ground_truth.tells)
        critic_matched_tells = list(
            dict.fromkeys(tell for tell in review.value.matched_tells if tell in allowed)
        )
        grade = merge_reasoning(
            grade,
            scenario,
            review.value.matched_tells,
            review.value.followup,
        )
        grade = grade.model_copy(
            update={
                "graded_by": self.settings.critic_model,
                "critic_used": True,
                "critic_model": self.settings.critic_model,
                "critic_response_id": review.response_id,
                "deterministic_matched_tells": deterministic_matched_tells,
                "critic_matched_tells": critic_matched_tells,
            }
        )
        logger.info(
            "Reasoning critic completed model=%s scenario_id=%s matched_count=%s response_id=%s",
            self.settings.critic_model,
            scenario.id,
            len(grade.matched_tells),
            review.response_id,
        )
        return grade
