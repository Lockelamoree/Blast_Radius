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
    ModelGeneratedPresentation,
    ModelReasoningReview,
    OpenAIAdapter,
    SessionLLMBudget,
    model_input,
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


def generated_presentation(scenario) -> dict:
    payload = scenario.presentation.model_dump(mode="json")
    payload["eyebrow"] = "Live variation · verified anchor"
    payload["agent_note"] = f"Reworded safely: {scenario.presentation.agent_note}"
    return payload


def test_grading_and_generation_schemas_are_strict(test_settings) -> None:
    engine = TrustEngine(test_settings)
    scenario = engine.bank.get("dep-typo-1")
    generated = ModelGeneratedPresentation.model_validate(
        generated_presentation(scenario)
    )

    for model in (ModelGateReview, ModelReasoningReview, ModelGeneratedPresentation):
        assert_strict_objects(to_strict_schema(model.model_json_schema()))

    assert generated.model_dump(mode="json") == generated_presentation(scenario)


def test_generated_schema_rejects_model_authored_identity_or_truth(test_settings) -> None:
    scenario = TrustEngine(test_settings).bank.get("dep-typo-1")
    payload = generated_presentation(scenario)
    payload["family"] = scenario.family.value
    with pytest.raises(ValidationError):
        ModelGeneratedPresentation.model_validate(payload)

    payload = generated_presentation(scenario)
    payload["ground_truth"] = scenario.ground_truth.model_dump(mode="json")
    with pytest.raises(ValidationError):
        ModelGeneratedPresentation.model_validate(payload)
    payload = generated_presentation(scenario)
    payload["artifacts"] = []
    with pytest.raises(ValidationError):
        ModelGeneratedPresentation.model_validate(payload)


class FakeResponses:
    def __init__(
        self,
        output_text: str | None = None,
        error: Exception | None = None,
        response_id: str | None = "resp_schema_test",
        response_model: str | None = None,
    ):
        self.output_text = output_text
        self.error = error
        self.response_id = response_id
        self.response_model = response_model
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            output_text=self.output_text,
            id=self.response_id,
            model=self.response_model or kwargs["model"],
        )


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


def test_failed_dispatched_call_keeps_budget_unit_and_logs_status(
    test_settings, tmp_path, caplog
) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    api_key = "sk-" + "proj-supersecret123456"
    learner_secret = "LEARNER_PRIVATE_VALUE_7391"
    settings = replace(test_settings, openai_api_key=api_key)
    adapter = OpenAIAdapter(
        settings,
        reserve_llm_call=lambda: store.reserve_llm_call(1),
        refund_llm_call=store.refund_llm_call,
    )
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    failure = BadRequestError(
        f"invalid model id reflected {learner_secret} and {api_key}",
        response=response,
        body=None,
    )
    fake = FakeResponses(error=failure)
    adapter._client = FakeClient(fake)

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            adapter._structured(
                model=settings.critic_model,
                prompt=model_input(
                    "Never reveal request content.",
                    {"learner_reasoning": learner_secret},
                ),
                output_type=ModelReasoningReview,
                name="test_review",
                effort="medium",
                max_output_tokens=512,
            )
        )

    assert result is None
    assert store.llm_usage() == 1
    assert "status=400" in caplog.text
    assert "invalid model id" in caplog.text
    assert learner_secret not in caplog.text
    assert api_key not in caplog.text
    assert "[REDACTED]" in caplog.text


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
            max_output_tokens=512,
            safety_identifier="session_123",
        )
    )

    assert result is not None
    assert result.response_id == "resp_schema_test"
    assert result.response_model == settings.critic_model
    assert store.llm_usage() == 1
    assert_strict_objects(fake.calls[0]["text"]["format"]["schema"])
    assert fake.calls[0]["store"] is False
    assert fake.calls[0]["max_output_tokens"] == 512
    assert fake.calls[0]["safety_identifier"] == "session_123"


def test_malformed_dispatched_response_keeps_budget_unit(test_settings, tmp_path) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(
        settings,
        reserve_llm_call=lambda: store.reserve_llm_call(1),
        refund_llm_call=store.refund_llm_call,
    )
    adapter._client = FakeClient(FakeResponses(output_text="not-json"))

    result = asyncio.run(
        adapter._structured(
            model=settings.critic_model,
            prompt="probe",
            output_type=ModelReasoningReview,
            name="test_review",
            effort="medium",
            max_output_tokens=settings.reasoning_max_output_tokens,
        )
    )

    assert result is None
    assert store.llm_usage() == 1


def test_generator_requests_presentation_only_with_its_role_bound(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key", live_generation=True)
    adapter = OpenAIAdapter(settings)
    scenario = TrustEngine(test_settings).bank.get("dep-typo-1")
    fake = FakeResponses(
        output_text=ModelGeneratedPresentation.model_validate(
            generated_presentation(scenario)
        ).model_dump_json()
    )
    adapter._client = FakeClient(fake)

    result = asyncio.run(
        adapter.generate(
            scenario,
            TrustEngine(test_settings).bank.templates[scenario.template_ref],
            difficulty=4,
            blind_spot="provenance",
            safety_identifier="session-test",
        )
    )

    assert result is not None
    request = fake.calls[0]
    assert request["max_output_tokens"] == settings.generator_max_output_tokens
    assert request["store"] is False
    assert request["safety_identifier"] == "session-test"
    properties = request["text"]["format"]["schema"]["properties"]
    assert set(properties) == {"eyebrow", "ask_text", "agent_note", "artifacts"}
    assert "ground_truth" not in properties
    assert result.eyebrow == "Live variation · verified anchor"
    assert result.ask_text == scenario.presentation.ask_text
    assert result.agent_note.startswith("Reworded safely:")


def test_generator_rejects_malformed_presentation(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key", live_generation=True)
    adapter = OpenAIAdapter(settings)
    engine = TrustEngine(test_settings)
    scenario = engine.bank.get("dep-typo-1")
    fake = FakeResponses(output_text='{"eyebrow":"missing everything else"}')
    adapter._client = FakeClient(fake)

    result = asyncio.run(
        adapter.generate(
            scenario,
            engine.bank.templates[scenario.template_ref],
            difficulty=4,
            blind_spot="provenance",
            safety_identifier="session-test",
        )
    )

    assert result is None


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


def test_missing_response_id_never_marks_probe_live(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(settings)
    adapter._client = FakeClient(
        FakeResponses(
            output_text=ModelReasoningReview(
                matched_tells=[],
                followup="Critic model is available.",
            ).model_dump_json(),
            response_id=None,
        )
    )

    asyncio.run(adapter.probe_reasoning_grading())

    assert adapter.reasoning_grading_state == "key_present_unverified"


@pytest.mark.parametrize("response_model", [None, "gpt-5.6-unexpected"])
def test_missing_or_mismatched_response_model_never_marks_probe_live(
    test_settings, response_model
) -> None:
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(settings)
    fake = FakeResponses(
        output_text=ModelReasoningReview(
            matched_tells=[],
            followup="Critic model is available.",
        ).model_dump_json(),
        response_model=response_model,
    )
    if response_model is None:
        async def create_without_model(**kwargs):
            fake.calls.append(kwargs)
            return SimpleNamespace(output_text=fake.output_text, id=fake.response_id)

        fake.create = create_without_model
    adapter._client = FakeClient(fake)

    asyncio.run(adapter.probe_reasoning_grading())

    assert adapter.reasoning_grading_state == "key_present_unverified"


def test_probe_failure_remains_unverified_and_is_cached(test_settings) -> None:
    settings = replace(test_settings, openai_api_key="test-key")
    fake = FakeResponses(output_text="not-json")
    adapter = OpenAIAdapter(settings)
    adapter._client = FakeClient(fake)

    asyncio.run(adapter.probe_reasoning_grading())
    asyncio.run(adapter.probe_reasoning_grading())

    assert adapter.reasoning_grading_state == "key_present_unverified"
    assert len(fake.calls) == 1


def test_reasoning_timeout_keeps_dispatched_attempt_and_falls_back(
    test_settings, tmp_path
) -> None:
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
    assert store.llm_usage() == 1


def test_pre_dispatch_failure_refunds_budget(test_settings, tmp_path) -> None:
    class LocallyFailingResponses:
        def create(self, **kwargs):
            raise RuntimeError("local request construction failed")

    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(
        settings,
        reserve_llm_call=lambda: store.reserve_llm_call(1),
        refund_llm_call=store.refund_llm_call,
    )
    adapter._client = FakeClient(LocallyFailingResponses())

    result = asyncio.run(
        adapter._structured(
            model=settings.critic_model,
            prompt="probe",
            output_type=ModelReasoningReview,
            name="test_review",
            effort="medium",
            max_output_tokens=512,
        )
    )

    assert result is None
    assert store.llm_usage() == 0


def test_pre_dispatch_failure_refunds_session_budget(test_settings) -> None:
    class LocallyFailingResponses:
        def create(self, **kwargs):
            raise RuntimeError("local request construction failed")

    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(settings)
    adapter._client = FakeClient(LocallyFailingResponses())
    session_budget = SessionLLMBudget(limit=1)

    result = asyncio.run(
        adapter._structured(
            model=settings.critic_model,
            prompt="probe",
            output_type=ModelReasoningReview,
            name="test_review",
            effort="medium",
            max_output_tokens=512,
            session_budget=session_budget,
        )
    )

    assert result is None
    assert session_budget.used == 0


def test_concurrent_dispatches_cannot_exceed_session_budget(test_settings) -> None:
    class SlowResponses(FakeResponses):
        async def create(self, **kwargs):
            self.calls.append(kwargs)
            await asyncio.sleep(0.02)
            return SimpleNamespace(
                output_text=ModelReasoningReview(
                    matched_tells=[],
                    followup="Review completed successfully.",
                ).model_dump_json(),
                id="resp_session_cap",
                model=kwargs["model"],
            )

    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(settings)
    fake = SlowResponses()
    adapter._client = FakeClient(fake)
    session_budget = SessionLLMBudget(limit=1)

    async def call_once():
        return await adapter._structured(
            model=settings.critic_model,
            prompt="probe",
            output_type=ModelReasoningReview,
            name="test_review",
            effort="medium",
            max_output_tokens=512,
            session_budget=session_budget,
        )

    async def run_both():
        return await asyncio.gather(call_once(), call_once())

    results = asyncio.run(run_both())

    assert sum(result is not None for result in results) == 1
    assert len(fake.calls) == 1
    assert session_budget.used == 1


def test_invalid_safety_identifier_never_dispatches_or_reserves(
    test_settings, tmp_path
) -> None:
    store = SessionStore(tmp_path / "budget.db", ttl_minutes=180)
    settings = replace(test_settings, openai_api_key="test-key")
    adapter = OpenAIAdapter(
        settings,
        reserve_llm_call=lambda: store.reserve_llm_call(1),
        refund_llm_call=store.refund_llm_call,
    )
    fake = FakeResponses(output_text="not used")
    adapter._client = FakeClient(fake)

    result = asyncio.run(
        adapter._structured(
            model=settings.critic_model,
            prompt="probe",
            output_type=ModelReasoningReview,
            name="test_review",
            effort="medium",
            max_output_tokens=512,
            safety_identifier="contains spaces",
        )
    )

    assert result is None
    assert fake.calls == []
    assert store.llm_usage() == 0


def test_openai_client_disables_automatic_retries(test_settings, monkeypatch) -> None:
    captured: dict = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", FakeAsyncOpenAI)
    OpenAIAdapter(replace(test_settings, openai_api_key="test-key"))

    assert captured["max_retries"] == 0


def test_startup_probe_does_not_block_application_start(test_settings, monkeypatch) -> None:
    async def slow_probe(self):
        await asyncio.sleep(60)

    monkeypatch.setattr(OpenAIAdapter, "probe_reasoning_grading", slow_probe)
    settings = replace(
        test_settings,
        openai_api_key="test-key",
        revision="abc123def456",
    )

    started = time.monotonic()
    with TestClient(create_app(settings)) as client:
        elapsed = time.monotonic() - started
        health = client.get("/healthz").json()

    assert elapsed < 1
    assert health["reasoning_grading"] == "key_present_unverified"
    assert health["revision"] == "abc123def456"
    assert "api_key" not in str(health).lower()
