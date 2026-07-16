import pytest
from pydantic import ValidationError

from blast_radius.engine.bank import ScenarioBank
from blast_radius.models import (
    BlastRadiusConfig,
    Evidence,
    GroundTruth,
    PlayerDecision,
    Receipt,
    TestQuestion as QuestionModel,
)


@pytest.mark.parametrize(
    "path",
    [
        "/workspace/../.ssh",
        "/workspace-escape/secrets",
        "/workspaceevil/secrets",
        "/workspace/src\\secrets",
        "/workspace/**",
        f"/workspace/{'x' * 500}",
    ],
)
def test_sandbox_paths_cannot_escape_or_ambiguate_workspace(path: str) -> None:
    with pytest.raises(ValidationError):
        BlastRadiusConfig(readable_paths=[path])


def test_sandbox_paths_are_canonicalized_and_deduplicated() -> None:
    config = BlastRadiusConfig(
        readable_paths=["/workspace/docs/", "/workspace/docs"]
    )

    assert config.readable_paths == ["/workspace/docs"]


def test_allowlist_requires_network() -> None:
    with pytest.raises(ValidationError):
        BlastRadiusConfig(network_enabled=False, network_allowlist=["example.com"])


@pytest.mark.parametrize(
    "host",
    [
        "*",
        "https://example.com",
        "example.com/path",
        "example.com:443",
        ".example.com",
        "example.com.",
        "bad host.example",
        "198.51.100.9",
        f"{'x' * 254}.example",
    ],
)
def test_allowlist_accepts_only_bounded_bare_hostnames(host: str) -> None:
    with pytest.raises(ValidationError):
        BlastRadiusConfig(network_enabled=True, network_allowlist=[host])


def test_allowlist_hostnames_are_canonicalized_and_deduplicated() -> None:
    config = BlastRadiusConfig(
        network_enabled=True,
        network_allowlist=["Docs.Example.com", "docs.example.com"],
    )

    assert config.network_allowlist == ["docs.example.com"]


@pytest.mark.parametrize(
    "capability",
    ["", "HTTP-GET", "read secrets", "read/secrets", "*", f"x{'a' * 80}"],
)
def test_capabilities_use_bounded_canonical_names(capability: str) -> None:
    with pytest.raises(ValidationError):
        BlastRadiusConfig(capabilities=[capability])


def test_capabilities_are_deduplicated() -> None:
    config = BlastRadiusConfig(capabilities=["http-get", "http-get"])

    assert config.capabilities == ["http-get"]


def test_sandbox_decision_requires_configuration() -> None:
    with pytest.raises(ValidationError):
        PlayerDecision(
            scenario_id="scenario-1",
            action="sandbox",
            reasoning_text="The write scope should be constrained.",
        )


def test_reasoning_has_minimum_signal() -> None:
    with pytest.raises(ValidationError):
        PlayerDecision(scenario_id="scenario-1", action="reject", reasoning_text="no")
    with pytest.raises(ValidationError):
        PlayerDecision(
            scenario_id="scenario-1",
            action="reject",
            reasoning_text="x       ",
        )


def test_non_sandbox_truth_rejects_a_safe_policy(test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    payload = bank.get("dep-typo-1").ground_truth.model_dump(mode="json")
    payload["safe_blast_radius"] = bank.get(
        "cmd-cleanup-2"
    ).ground_truth.safe_blast_radius.model_dump(mode="json")

    with pytest.raises(ValidationError, match="only sandbox"):
        GroundTruth.model_validate(payload)


def test_question_rejects_unknown_competency() -> None:
    with pytest.raises(ValidationError):
        QuestionModel(
            id="q-unknown",
            prompt="Which competency does this question test?",
            options=["Known", "Unknown"],
            correct_index=0,
            competency="raw tell string",
            form="pre",
        )


def test_question_rejects_out_of_range_correct_index() -> None:
    with pytest.raises(ValidationError):
        QuestionModel(
            id="q-invalid-index",
            prompt="Which answer is available?",
            options=["First", "Second"],
            correct_index=2,
            competency="scope",
            form="pre",
        )


def test_question_requires_a_form_and_unique_nonblank_options() -> None:
    with pytest.raises(ValidationError):
        QuestionModel(
            id="q-missing-form",
            prompt="Which answer is available?",
            options=["First", "Second"],
            correct_index=0,
            competency="scope",
        )
    with pytest.raises(ValidationError):
        QuestionModel(
            id="q-duplicate-options",
            prompt="Which answer is available?",
            options=["First", "First"],
            correct_index=0,
            competency="scope",
            form="pre",
        )
    with pytest.raises(ValidationError):
        QuestionModel(
            id="q-blank-option",
            prompt="Which answer is available?",
            options=["First", "   "],
            correct_index=0,
            competency="scope",
            form="pre",
        )


def test_question_keeps_assessment_form_internal() -> None:
    question = QuestionModel(
        id="q-post",
        prompt="Which answer is available?",
        options=["First", "Second"],
        correct_index=1,
        competency="scope",
        form="post",
    )

    assert question.form.value == "post"
    assert "correct_index" not in question.public_view()
    assert "form" not in question.public_view()


def test_ground_truth_rejects_blank_tell_keywords(test_settings) -> None:
    scenario = ScenarioBank(test_settings.data_dir).get("cmd-exfil-1")
    payload = scenario.ground_truth.model_dump(mode="json")
    payload["tell_keywords"][scenario.ground_truth.tells[0]] = ["   "]

    with pytest.raises(ValidationError):
        GroundTruth.model_validate(payload)


@pytest.mark.parametrize("source", ["javascript:alert(1)", "data:text/html,payload"])
def test_evidence_and_receipts_reject_unsafe_source_schemes(source: str) -> None:
    with pytest.raises(ValidationError):
        Evidence(
            id="unsafe-source",
            source=source,
            retrieved_at="2026-07-15",
            claim="This claim has a sufficiently descriptive body.",
            excerpt="A supporting artifact excerpt.",
        )
    with pytest.raises(ValidationError):
        Receipt(claim="Unsafe source", evidence="Artifact", source=source)


def test_evidence_and_receipts_accept_https_sources() -> None:
    source = "https://example.com/security/advisory"
    assert Evidence(
        id="safe-source",
        source=source,
        retrieved_at="2026-07-15",
        claim="This claim has a sufficiently descriptive body.",
        excerpt="A supporting artifact excerpt.",
    ).source == source
    assert Receipt(claim="Safe source", evidence="Artifact", source=source).source == source
