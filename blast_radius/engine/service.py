from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from blast_radius.config import Settings
from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.gate import CorrectnessGate
from blast_radius.engine.grader import grade_decision, merge_reasoning
from blast_radius.engine.openai_adapter import (
    CRITIC_REASONING_EFFORT,
    OpenAIAdapter,
    SessionLLMBudget,
)
from blast_radius.models import (
    GenerationStatus,
    GradeResult,
    PlayerDecision,
    Scenario,
    ScenarioFamily,
    ScenarioProvenance,
)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("uvicorn.error")


def audit_session_hash(session_id: str | None) -> str:
    if not session_id:
        return "none"
    return hashlib.sha256(f"blast-radius-audit:v1:{session_id}".encode()).hexdigest()


@dataclass(frozen=True)
class ScenarioSelection:
    scenario: Scenario
    anchor_id: str
    provenance: ScenarioProvenance
    generation_status: GenerationStatus
    failure_reason: str | None = None

    def __iter__(self):
        """Keep the historical scenario/failure tuple unpacking available internally."""
        yield self.scenario
        yield self.failure_reason


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

    def live_generation_availability(self, daily_budget_remaining: int) -> tuple[bool, str]:
        if not self.settings.live_generation or not self.settings.openai_api_key:
            return False, "off"
        if self.openai.reasoning_grading_state != "live":
            return False, "critic_unverified"
        if daily_budget_remaining <= 0:
            return False, "budget_exhausted"
        if daily_budget_remaining <= self.settings.generation_budget_reserve:
            # The tail of the daily budget belongs to grading, never generation.
            return False, "grading_reserved"
        return True, "available"

    @staticmethod
    def _generation_status_from_failure(failure: str | None) -> GenerationStatus:
        return (
            GenerationStatus.BUDGET_EXHAUSTED
            if failure == "budget_exhausted"
            else GenerationStatus.FELL_BACK
        )

    @staticmethod
    def _rejection_category(
        failure_reason: str | None, status: GenerationStatus
    ) -> str:
        """Reduce failure detail to an audit-safe category before logging."""
        if failure_reason is None:
            return "none"
        if status == GenerationStatus.TIMEOUT:
            return "timeout"
        if status == GenerationStatus.BUDGET_EXHAUSTED:
            return "budget_exhausted"
        if failure_reason in {
            "off",
            "critic_unverified",
            "round_cap",
            "grading_reserved",
            "provider_error",
            "malformed_response",
            "invalid_request",
            "invalid_schema",
            "unavailable",
        }:
            return failure_reason
        if "generated" in failure_reason or "presented artifacts" in failure_reason:
            return "deterministic_gate"
        if failure_reason.startswith("no compatible curated base"):
            return "anchor_unavailable"
        if failure_reason.startswith("curated base references"):
            return "template_unavailable"
        if failure_reason == "critic correctness gate unavailable":
            return "critic_unavailable"
        if failure_reason == "live generation unavailable":
            return "generator_unavailable"
        return "critic_rejected"

    def _selection(
        self,
        *,
        scenario: Scenario,
        anchor_id: str,
        status: GenerationStatus,
        failure_reason: str | None,
        safety_identifier: str | None,
        calls_before: int,
        session_budget: SessionLLMBudget | None,
        log_attempt: bool,
    ) -> ScenarioSelection:
        provenance = (
            ScenarioProvenance.GENERATED
            if status == GenerationStatus.GENERATED
            else ScenarioProvenance.VERIFIED
        )
        if log_attempt:
            calls_after = session_budget.used if session_budget is not None else calls_before
            logger.info(
                "Live variation session_sha256=%s anchor_id=%s status=%s calls=%s "
                "generated_id=%s rejection=%s",
                audit_session_hash(safety_identifier),
                anchor_id,
                status.value,
                max(0, calls_after - calls_before),
                scenario.id if provenance == ScenarioProvenance.GENERATED else "none",
                self._rejection_category(failure_reason, status),
            )
        return ScenarioSelection(
            scenario=scenario,
            anchor_id=anchor_id,
            provenance=provenance,
            generation_status=status,
            failure_reason=failure_reason,
        )

    async def next_scenario(
        self,
        *,
        family: ScenarioFamily | None,
        difficulty: int,
        blind_spot: str,
        exclude: set[str],
        seed: str,
        competency: dict[str, dict[str, int]] | None = None,
        safety_identifier: str | None = None,
        generation_requested: bool = True,
        generation_available: bool | None = None,
        generation_unavailable_reason: str = "off",
        session_budget: SessionLLMBudget | None = None,
    ) -> ScenarioSelection:
        _ = competency  # Backward-compatible input; targeting is now the clamped blind_spot label.
        failure_reason: str | None = None
        fallback = self.bank.fallback(family=family, exclude=exclude, seed=seed)
        fallback_result = self.gate.verify(fallback)
        if not fallback_result.passed:
            raise RuntimeError(f"verified fallback failed gate: {fallback_result.reasons}")

        calls_before = session_budget.used if session_budget is not None else 0
        if not generation_requested:
            return self._selection(
                scenario=fallback,
                anchor_id=fallback.id,
                status=GenerationStatus.NOT_REQUESTED,
                failure_reason=None,
                safety_identifier=safety_identifier,
                calls_before=calls_before,
                session_budget=session_budget,
                log_attempt=False,
            )

        if generation_available is None:
            generation_available = self.openai.generation_enabled
        if not generation_available:
            failure_reason = generation_unavailable_reason
            return self._selection(
                scenario=fallback,
                anchor_id=fallback.id,
                status=self._generation_status_from_failure(failure_reason),
                failure_reason=failure_reason,
                safety_identifier=safety_identifier,
                calls_before=calls_before,
                session_budget=session_budget,
                log_attempt=True,
            )

        if self.openai.generation_enabled and family is not None:
            if fallback.family != family:
                failure_reason = "no compatible curated base remains in the requested family"
            else:
                template = self.bank.templates.get(fallback.template_ref)
                if template is None:
                    failure_reason = "curated base references an unknown template"
                    return self._selection(
                        scenario=fallback,
                        anchor_id=fallback.id,
                        status=GenerationStatus.FELL_BACK,
                        failure_reason=failure_reason,
                        safety_identifier=safety_identifier,
                        calls_before=calls_before,
                        session_budget=session_budget,
                        log_attempt=True,
                    )
                try:
                    async with asyncio.timeout(self.settings.generation_timeout_seconds):
                        generation_budget = (
                            {"session_budget": session_budget}
                            if session_budget is not None
                            else {}
                        )
                        presentation = await self.openai.generate(
                            fallback,
                            template,
                            difficulty,
                            blind_spot,
                            safety_identifier=safety_identifier,
                            **generation_budget,
                        )
                except TimeoutError:
                    failure_reason = "generation timeout"
                    return self._selection(
                        scenario=fallback,
                        anchor_id=fallback.id,
                        status=GenerationStatus.TIMEOUT,
                        failure_reason=failure_reason,
                        safety_identifier=safety_identifier,
                        calls_before=calls_before,
                        session_budget=session_budget,
                        log_attempt=True,
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
                        try:
                            async with asyncio.timeout(self.settings.generation_timeout_seconds):
                                critic_budget = (
                                    {"session_budget": session_budget}
                                    if session_budget is not None
                                    else {}
                                )
                                critic_result = await self.openai.critic_gate(
                                    generated,
                                    template,
                                    safety_identifier=safety_identifier,
                                    **critic_budget,
                                )
                        except TimeoutError:
                            failure_reason = "critic gate timeout"
                            return self._selection(
                                scenario=fallback,
                                anchor_id=fallback.id,
                                status=GenerationStatus.TIMEOUT,
                                failure_reason=failure_reason,
                                safety_identifier=safety_identifier,
                                calls_before=calls_before,
                                session_budget=session_budget,
                                log_attempt=True,
                            )
                        critic = critic_result.value if critic_result else None
                        if critic and critic.passed:
                            return self._selection(
                                scenario=generated,
                                anchor_id=fallback.id,
                                status=GenerationStatus.GENERATED,
                                failure_reason=None,
                                safety_identifier=safety_identifier,
                                calls_before=calls_before,
                                session_budget=session_budget,
                                log_attempt=True,
                            )
                        failure_reason = (
                            "; ".join(critic.reasons)
                            if critic
                            else self.openai.last_failure
                            or "critic correctness gate unavailable"
                        )
                    else:
                        failure_reason = "; ".join(result.reasons)
                else:
                    failure_reason = self.openai.last_failure or "live generation unavailable"
        return self._selection(
            scenario=fallback,
            anchor_id=fallback.id,
            status=self._generation_status_from_failure(failure_reason),
            failure_reason=failure_reason,
            safety_identifier=safety_identifier,
            calls_before=calls_before,
            session_budget=session_budget,
            log_attempt=True,
        )

    async def grade(
        self,
        scenario: Scenario,
        decision: PlayerDecision,
        *,
        safety_identifier: str | None = None,
        allow_critic: bool = True,
        session_budget: SessionLLMBudget | None = None,
    ) -> GradeResult:
        grade = grade_decision(scenario, decision)
        if not allow_critic or not self.openai.grading_enabled:
            return grade
        critique_started = time.perf_counter()
        try:
            critique_budget = (
                {"session_budget": session_budget}
                if session_budget is not None
                else {}
            )
            review = await self.openai.critique_reasoning(
                scenario,
                decision,
                safety_identifier=safety_identifier,
                **critique_budget,
            )
        except Exception as exc:
            logger.warning("OpenAI reasoning critique failed (%s)", type(exc).__name__)
            return grade.model_copy(update={"grading_degraded_reason": "critic_error"})
        critique_latency_ms = round((time.perf_counter() - critique_started) * 1000)
        if review is None:
            if getattr(self.openai, "budget_exhausted", False):
                return grade.model_copy(
                    update={"grading_degraded_reason": "budget_exhausted"}
                )
            last_failure = getattr(self.openai, "last_failure", None)
            return grade.model_copy(
                update={
                    "grading_degraded_reason": (
                        "critic_timeout" if last_failure is None else f"critic_{last_failure}"
                    )
                }
            )
        allowed = set(scenario.ground_truth.tells)
        critic_matched_tells = list(
            dict.fromkeys(tell for tell in review.value.matched_tells if tell in allowed)
        )
        followup = review.value.followup.strip()
        # Only a real second-person question may replace the deterministic
        # Socratic prompt; grader rubric-speak keeps the curated question.
        if not followup.endswith("?") or followup.lower().startswith("the learner"):
            followup = None
        grade = merge_reasoning(
            grade,
            scenario,
            review.value.matched_tells,
            followup,
        )
        grade = grade.model_copy(
            update={
                "graded_by": review.response_model,
                "critic_used": True,
                "critic_model": review.response_model,
                "critic_response_id": review.response_id,
                "critic_effort": CRITIC_REASONING_EFFORT,
                "critic_latency_ms": critique_latency_ms,
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
