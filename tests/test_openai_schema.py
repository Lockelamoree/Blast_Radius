import asyncio
import logging
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import BadRequestError
from pydantic import ValidationError

from blast_radius.engine.openai_adapter import (
    ModelGateReview,
    ModelGeneratedScenario,
    ModelReasoningReview,
    OpenAIAdapter,
    to_strict_schema,
)
from blast_radius.engine.service import TrustEngine
from blast_radius.main import create_app
from blast_radius.models import PlayerDecision
from blast_radius.storage import SessionStore


def assert_strict_objects(node) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node.get("properties", {}))
        for value in node.values():
            assert_strict_objects(value)
    elif isinstance(node, list):
        for value in node:
            assert_strict_objects(value)


def model_generated_payload(scenario) -> dict:
    payload = scenario.model_dump(mode="json")
    payload["ground_truth"]["tell_keywords"] = [
        {"tell": tell, "keywords": keywords}
        for tell, keywords in scenario.ground_truth.tell_keywords.items()
    ]
    return payload


def test_grading_and_generation_schemas_are_strict(test_settings) -> None:
    engine = TrustEngine(test_settings)
    scenario = engine.bank.get("dep-typo-1")
    generated = ModelGeneratedScenario.model_validate(model_generated_payload(scenario))

    for model in (ModelGateReview, ModelReasoningReview, ModelGeneratedScenario):
        assert_strict_objects(to_strict_schema(model.model_json_schema()))

    converted = generated.to_scenario()
    assert converted == scenario
    assert isinstance(converted.ground_truth.tell_keywords, dict)


def test_generated_schema_rejects_duplicate_or_missing_tell_groups(test_settings) -> None:
    scenario = TrustEngine(test_settings).bank.get("dep-typo-1")
    payload = model_generated_payload(scenario)
    payload["ground_truth"]["tell_keywords"][1]["tell"] = payload["ground_truth"][
        "tell_keywords"
    ][0]["tell"]
    with pytest.raises(ValidationError):
        ModelGeneratedScenario.model_validate(payload)

    payload = model_generated_payload(scenario)
    payload["ground_truth"]["tell_keywords"].pop()
    with pytest.raises(ValidationError):
        ModelGeneratedScenario.model_validate(payload)


class FakeResponses:
    def __init__(self, output_text: str | None = None, error: Exception | None = None):
        self.output_text = output_text
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_text=self.output_text, id="resp_schema_test")


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


def test_failed_structured_call_refunds_budget_and_logs_status(
    test_settings, tmp_path, caplog
) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(
        settings,
        reserve_llm_call=lambda: store.reserve_llm_call(1),
        refund_llm_call=store.refund_llm_call,
    )
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    failure = BadRequestError("invalid model id", response=response, body=None)
    fake = FakeResponses(error=failure)
    adapter._client = FakeClient(fake)

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            adapter._structured(
                model=settings.critic_model,
                prompt="secret prompt must not be logged",
                output_type=ModelReasoningReview,
                name="test_review",
                effort="medium",
            )
        )

    assert result is None
    assert store.llm_usage() == 0
    assert "status=400" in caplog.text
    assert "invalid model id" in caplog.text
    assert "secret prompt" not in caplog.text


def test_successful_structured_call_consumes_one_budget_unit(test_settings, tmp_path) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(
        settings,
        reserve_llm_call=lambda: store.reserve_llm_call(1),
        refund_llm_call=store.refund_llm_call,
    )
    fake = FakeResponses(
        output_text=ModelReasoningReview(
            matched_tells=[],
            followup="Review completed successfully.",
        ).model_dump_json()
    )
    adapter._client = FakeClient(fake)

    result = asyncio.run(
        adapter._structured(
            model=settings.critic_model,
            prompt="probe",
            output_type=ModelReasoningReview,
            name="test_review",
            effort="medium",
        )
    )

    assert result is not None
    assert result.response_id == "resp_schema_test"
    assert store.llm_usage() == 1
    assert_strict_objects(fake.calls[0]["text"]["format"]["schema"])


def test_probe_reports_live_only_after_valid_response(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(settings)
    adapter._client = FakeClient(
        FakeResponses(
            output_text=ModelReasoningReview(
                matched_tells=[],
                followup="Critic model is available.",
            ).model_dump_json()
        )
    )

    assert adapter.reasoning_grading_state == "key_present_unverified"
    asyncio.run(adapter.probe_reasoning_grading())
    assert adapter.reasoning_grading_state == "live"


def test_probe_failure_remains_unverified_and_is_cached(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key")
    fake = FakeResponses(output_text="not-json")
    adapter = OpenAIAdapter(settings)
    adapter._client = FakeClient(fake)

    asyncio.run(adapter.probe_reasoning_grading())
    asyncio.run(adapter.probe_reasoning_grading())

    assert adapter.reasoning_grading_state == "key_present_unverified"
    assert len(fake.calls) == 1


def test_reasoning_timeout_refunds_and_falls_back(test_settings, tmp_path) -> None:
    class SlowResponses:
        async def create(self, **kwargs):
            await asyncio.sleep(1)

    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    settings = replace(
        test_settings,
        openai_api_key="test-key",
        critic_timeout_seconds=0.01,
    )
    adapter = OpenAIAdapter(
        settings,
        reserve_llm_call=lambda: store.reserve_llm_call(1),
        refund_llm_call=store.refund_llm_call,
    )
    adapter._client = FakeClient(SlowResponses())
    scenario = TrustEngine(test_settings).bank.get("dep-typo-1")
    decision = PlayerDecision(
        scenario_id=scenario.id,
        action="reject",
        reasoning_text="The package name is a suspicious near miss.",
    )

    result = asyncio.run(adapter.critique_reasoning(scenario, decision))

    assert result is None
    assert store.llm_usage() == 0


def test_startup_probe_does_not_block_application_start(test_settings, monkeypatch) -> None:
    async def slow_probe(self):
        await asyncio.sleep(60)

    monkeypatch.setattr(OpenAIAdapter, "probe_reasoning_grading", slow_probe)
    settings = replace(test_settings, openai_api_key="test-key")

    started = time.monotonic()
    with TestClient(create_app(settings)) as client:
        elapsed = time.monotonic() - started
        health = client.get("/healthz").json()

    assert elapsed < 1
    assert health["reasoning_grading"] == "key_present_unverified"
    assert "api_key" not in str(health).lower()
