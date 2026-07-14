import pytest
from pydantic import ValidationError

from blast_radius.models import BlastRadiusConfig, PlayerDecision


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

