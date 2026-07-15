import pytest
from pydantic import ValidationError

from blast_radius.models import (
    BlastRadiusConfig,
    Evidence,
    PlayerDecision,
    Receipt,
    TestQuestion as QuestionModel,
)


def test_sandbox_paths_cannot_escape_workspace() -> None:
    with pytest.raises(ValidationError):
        BlastRadiusConfig(readable_paths=["/workspace/../.ssh"])


def test_allowlist_requires_network() -> None:
    with pytest.raises(ValidationError):
        BlastRadiusConfig(network_enabled=False, network_allowlist=["example.com"])


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


def test_question_rejects_unknown_competency() -> None:
    with pytest.raises(ValidationError):
        QuestionModel(
            id="q-unknown",
            prompt="Which competency does this question test?",
            options=["Known", "Unknown"],
            correct_index=0,
            competency="raw tell string",
        )


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
