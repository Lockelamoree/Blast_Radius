from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from uuid import uuid4

from blast_radius.config import Settings
from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.gate import CorrectnessGate
from blast_radius.engine.grader import grade_decision, merge_reasoning
from blast_radius.engine.openai_adapter import OpenAIAdapter
from blast_radius.models import GradeResult, PlayerDecision, Scenario, ScenarioFamily

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("uvicorn.error")


def audit_session_hash(session_id: str | None) -> str:
    if not session_id:
        return "none"
    return hashlib.sha256(f"blast-radius-audit:v1:{session_id}".encode()).hexdigest()


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
        safety_identifier: str | None = None,
    ) -> tuple[Scenario, str | None]:
        failure_reason: str | None = None
        fallback = self.bank.fallback(family=family, exclude=exclude, seed=seed)
        fallback_result = self.gate.verify(fallback)
        if not fallback_result.passed:
            raise RuntimeError(f"verified fallback failed gate: {fallback_result.reasons}")

        if self.openai.generation_enabled and family is not None:
            if fallback.family != family:
                failure_reason = "no compatible curated base remains in the requested family"
            else:
                template = self.bank.templates.get(fallback.template_ref)
                if template is None:
                    return fallback, "curated base references an unknown template"
                blind_spot = await self.openai.adapt_blind_spot(
                    competency,
                    blind_spot,
                    safety_identifier=safety_identifier,
                )
                presentation = await self.openai.generate(
                    fallback,
                    template,
                    difficulty,
                    blind_spot,
                    safety_identifier=safety_identifier,
                )
                if presentation:
                    generated_id = f"live-{uuid4().hex}"
                    while generated_id in self.bank.scenarios or generated_id in exclude:
                        generated_id = f"live-{uuid4().hex}"
                    generated = Scenario(
                        id=generated_id,
                        family=fallback.family,
                        template_ref=fallback.template_ref,
                        difficulty=difficulty,
                        presentation=presentation,
                        ground_truth=fallback.ground_truth.model_copy(deep=True),
                    )
                    result = self.gate.verify(generated, trusted_base=fallback)
                    if result.passed:
                        critic_result = await self.openai.critic_gate(
                            generated,
                            template,
                            safety_identifier=safety_identifier,
                        )
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
        return fallback, failure_reason

    async def grade(
        self,
        scenario: Scenario,
        decision: PlayerDecision,
        *,
        safety_identifier: str | None = None,
    ) -> GradeResult:
        grade = grade_decision(scenario, decision)
        deterministic_matched_tells = list(grade.matched_tells)
        if not self.openai.grading_enabled:
            return grade
        try:
            review = await self.openai.critique_reasoning(
                scenario,
                decision,
                safety_identifier=safety_identifier,
            )
        except Exception as exc:
            logger.warning("OpenAI reasoning critique failed (%s)", type(exc).__name__)
            return grade
        if review is None:
            if getattr(self.openai, "budget_exhausted", False):
                return grade.model_copy(
                    update={"grading_degraded_reason": "budget_exhausted"}
                )
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
                "graded_by": review.response_model,
                "critic_used": True,
                "critic_model": review.response_model,
                "critic_response_id": review.response_id,
                "deterministic_matched_tells": deterministic_matched_tells,
                "critic_matched_tells": critic_matched_tells,
            }
        )
        audit_logger.info(
            "Reasoning critic completed requested_model=%s provider_model=%s revision=%s "
            "session_sha256=%s scenario_id=%s matched_count=%s response_id=%s",
            self.settings.critic_model,
            review.response_model,
            self.settings.revision,
            audit_session_hash(safety_identifier),
            scenario.id,
            len(grade.matched_tells),
            review.response_id,
        )
        return grade
