import asyncio
import logging
from dataclasses import replace
from types import SimpleNamespace

from blast_radius.engine.openai_adapter import (
    ModelReasoningReview,
    StructuredCallResult,
)
from blast_radius.engine.service import TrustEngine
from blast_radius.models import PlayerDecision


class StubReasoningAdapter:
    grading_enabled = True
    generation_enabled = False

    async def critique_reasoning(self, scenario, decision):
        return StructuredCallResult(
            value=ModelReasoningReview(
                matched_tells=[scenario.ground_truth.tells[0], "invented tell"],
                followup="Which artifact proves the package name is a near miss?",
            ),
            response_id="resp_stub",
        )


class RaisingReasoningAdapter:
    grading_enabled = True
    generation_enabled = False

    async def critique_reasoning(self, scenario, decision):
        raise RuntimeError("simulated provider failure")


class FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text, id="resp_test")


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


def weak_decision(scenario) -> PlayerDecision:
    return PlayerDecision(
        scenario_id=scenario.id,
        action="reject",
        reasoning_text="This does not feel like the right choice to me.",
    )


def test_model_review_widens_validated_tells_and_identifies_grader(
    test_settings, caplog
) -> None:
    engine = TrustEngine(test_settings)
    scenario = engine.bank.get("dep-typo-1")
    engine.openai = StubReasoningAdapter()

    with caplog.at_level(logging.INFO):
        grade = asyncio.run(engine.grade(scenario, weak_decision(scenario)))

    assert grade.matched_tells == ["near-miss package name"]
    assert "invented tell" not in grade.matched_tells
    assert grade.reasoning_score == 50
    assert grade.graded_by == "gpt-5.6-sol"
    assert grade.critic_used
    assert grade.critic_model == "gpt-5.6-sol"
    assert grade.critic_response_id == "resp_stub"
    assert grade.deterministic_matched_tells == []
    assert grade.critic_matched_tells == ["near-miss package name"]
    assert grade.action_correct
    assert grade.receipts
    assert "scenario_id=dep-typo-1" in caplog.text
    assert "response_id=resp_stub" in caplog.text


def test_model_review_failure_falls_back_to_deterministic(test_settings) -> None:
    engine = TrustEngine(test_settings)
    scenario = engine.bank.get("dep-typo-1")
    engine.openai = RaisingReasoningAdapter()

    grade = asyncio.run(engine.grade(scenario, weak_decision(scenario)))

    assert grade.matched_tells == []
    assert grade.reasoning_score == 0
    assert grade.graded_by == "deterministic"
    assert not grade.critic_used
    assert grade.critic_response_id is None
    assert grade.verdict == "partial"


def test_key_enables_one_sol_grade_call_without_live_generation(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key", live_generation=False)
    engine = TrustEngine(settings, reserve_llm_call=lambda: "2026-07-15")
    scenario = engine.bank.get("dep-typo-1")
    responses = FakeResponses(
        ModelReasoningReview(
            matched_tells=["near-miss package name"],
            followup="Which artifact proves the package name is a near miss?",
        ).model_dump_json()
    )
    engine.openai._client = FakeClient(responses)

    grade = asyncio.run(engine.grade(scenario, weak_decision(scenario)))

    assert engine.openai.grading_enabled
    assert not engine.openai.generation_enabled
    assert len(responses.calls) == 1
    assert responses.calls[0]["model"] == "gpt-5.6-sol"
    assert responses.calls[0]["reasoning"] == {"effort": "medium"}
    assert grade.graded_by == "gpt-5.6-sol"
    assert grade.critic_used
    assert grade.critic_response_id == "resp_test"


def test_exhausted_budget_skips_provider_and_uses_deterministic_grade(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key", live_generation=False)
    engine = TrustEngine(settings, reserve_llm_call=lambda: None)
    scenario = engine.bank.get("dep-typo-1")
    responses = FakeResponses("this must never be parsed")
    engine.openai._client = FakeClient(responses)

    grade = asyncio.run(engine.grade(scenario, weak_decision(scenario)))

    assert responses.calls == []
    assert grade.graded_by == "deterministic"
    assert not grade.critic_used
    assert grade.reasoning_score == 0
