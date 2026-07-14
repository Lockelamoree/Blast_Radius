from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Action(StrEnum):
    APPROVE = "approve"
    SANDBOX = "sandbox"
    REJECT = "reject"


class ScenarioFamily(StrEnum):
    DANGEROUS_COMMAND = "dangerous_command"
    POISONED_DEPENDENCY = "poisoned_dependency"
    OVERSCOPED_TOOL = "overscoped_tool"
    MALICIOUS_DIFF = "malicious_diff"
    POISONED_CONTEXT = "poisoned_context"
    SKILL_MARKETPLACE = "skill_marketplace"


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=1, max_length=8000)
    language: str = Field(default="text", max_length=30)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    source: str = Field(min_length=8, max_length=500)
    retrieved_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    claim: str = Field(min_length=10, max_length=500)
    excerpt: str = Field(min_length=3, max_length=1000)


class BlastRadiusConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readable_paths: list[str] = Field(default_factory=list, max_length=12)
    writable_paths: list[str] = Field(default_factory=list, max_length=12)
    network_enabled: bool = False
    network_allowlist: list[str] = Field(default_factory=list, max_length=12)
    capabilities: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("readable_paths", "writable_paths")
    @classmethod
    def validate_paths(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if not path.startswith("/workspace") or ".." in path or "~" in path:
                raise ValueError("sandbox paths must stay below /workspace")
        return paths

    @field_validator("network_allowlist")
    @classmethod
    def validate_hosts(cls, hosts: list[str]) -> list[str]:
        for host in hosts:
            if not host or "/" in host or ":" in host or host.startswith("."):
                raise ValueError("allowlist entries must be bare hostnames")
        return hosts

    @model_validator(mode="after")
    def allowlist_requires_network(self) -> "BlastRadiusConfig":
        if self.network_allowlist and not self.network_enabled:
            raise ValueError("network allowlist requires network access")
        return self


class Presentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eyebrow: str = Field(min_length=2, max_length=80)
    ask_text: str = Field(min_length=10, max_length=1000)
    agent_note: str = Field(min_length=2, max_length=500)
    artifacts: list[Artifact] = Field(min_length=1, max_length=5)


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correct_action: Action
    safe_blast_radius: BlastRadiusConfig | None = None
    tells: list[str] = Field(min_length=1, max_length=8)
    tell_keywords: dict[str, list[str]] = Field(min_length=1, max_length=8)
    evidence: list[Evidence] = Field(min_length=1, max_length=8)
    explanation: str = Field(min_length=20, max_length=1500)

    @model_validator(mode="after")
    def sandbox_requires_policy(self) -> "GroundTruth":
        if self.correct_action == Action.SANDBOX and self.safe_blast_radius is None:
            raise ValueError("sandbox ground truth requires a safe blast radius")
        return self


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    family: ScenarioFamily
    template_ref: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    difficulty: int = Field(ge=1, le=5)
    presentation: Presentation
    ground_truth: GroundTruth

    def public_view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family.value,
            "difficulty": self.difficulty,
            "presentation": self.presentation.model_dump(mode="json"),
        }


class PlayerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    action: Action
    reasoning_text: str = Field(min_length=8, max_length=500)
    blast_radius_config: BlastRadiusConfig | None = None

    @field_validator("reasoning_text")
    @classmethod
    def normalize_reasoning(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def sandbox_config_matches_action(self) -> "PlayerDecision":
        if self.action == Action.SANDBOX and self.blast_radius_config is None:
            raise ValueError("sandbox decisions require a blast radius configuration")
        if self.action != Action.SANDBOX and self.blast_radius_config is not None:
            raise ValueError("blast radius configuration is only valid for sandbox")
        return self


class GateResult(BaseModel):
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    scenario_id: str | None = None


class Receipt(BaseModel):
    claim: str
    evidence: str
    source: str


class GradeResult(BaseModel):
    scenario_id: str
    verdict: str = Field(pattern=r"^(correct|partial|wrong)$")
    action_correct: bool
    reasoning_score: int = Field(ge=0, le=100)
    blast_radius_score: int | None = Field(default=None, ge=0, le=100)
    matched_tells: list[str]
    missed_tells: list[str]
    receipts: list[Receipt]
    explanation: str
    socratic_followup: str


class TestQuestion(BaseModel):
    id: str
    prompt: str
    options: list[str] = Field(min_length=2, max_length=5)
    correct_index: int = Field(ge=0)
    competency: str

    def public_view(self) -> dict[str, Any]:
        return self.model_dump(exclude={"correct_index"})


class SessionState(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: str = Field(pattern=r"^(demo|live)$")
    pretest_answers: list[int] | None = None
    pretest_score: int | None = None
    posttest_answers: list[int] | None = None
    posttest_score: int | None = None
    scenario_order: list[str]
    current_index: int = 0
    active_scenario_id: str | None = None
    active_scenario_json: str | None = None
    last_gate_fallback_reason: str | None = None
    answered_scenario_ids: list[str] = Field(default_factory=list)
    grades: list[GradeResult] = Field(default_factory=list)
    competency: dict[str, dict[str, int]] = Field(default_factory=dict)


class LearnerProgress(BaseModel):
    session_id: str
    pretest_score: int
    posttest_score: int
    delta: int
    rounds_played: int
    competency_map: dict[str, dict[str, int]]
    average_reasoning_score: int
    share_text: str
