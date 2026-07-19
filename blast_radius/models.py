from __future__ import annotations

import ipaddress
import posixpath
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

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


class Competency(StrEnum):
    SCOPE = "scope"
    PROVENANCE = "provenance"
    CAPABILITIES = "capabilities"
    DIFF_REVIEW = "diff_review"
    PROMPT_INJECTION = "prompt_injection"


class AssessmentForm(StrEnum):
    PRE = "pre"
    POST = "post"


class ScenarioProvenance(StrEnum):
    GENERATED = "generated"
    VERIFIED = "verified"


class GenerationStatus(StrEnum):
    GENERATED = "generated"
    FELL_BACK = "fell_back"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NOT_REQUESTED = "not_requested"


COMPETENCY_LABELS: dict[Competency, str] = {
    Competency.SCOPE: "Scope discipline",
    Competency.PROVENANCE: "Dependency provenance",
    Competency.CAPABILITIES: "Capability boundaries",
    Competency.DIFF_REVIEW: "Diff review",
    Competency.PROMPT_INJECTION: "Prompt injection",
}

FAMILY_COMPETENCIES: dict[ScenarioFamily, Competency] = {
    ScenarioFamily.DANGEROUS_COMMAND: Competency.SCOPE,
    ScenarioFamily.POISONED_DEPENDENCY: Competency.PROVENANCE,
    ScenarioFamily.OVERSCOPED_TOOL: Competency.CAPABILITIES,
    ScenarioFamily.MALICIOUS_DIFF: Competency.DIFF_REVIEW,
    ScenarioFamily.POISONED_CONTEXT: Competency.PROMPT_INJECTION,
    ScenarioFamily.SKILL_MARKETPLACE: Competency.CAPABILITIES,
}


def competency_for_family(family: ScenarioFamily) -> Competency:
    return FAMILY_COMPETENCIES[family]


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

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("evidence source must be an http(s) URL")
        return value


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
        normalized_paths: list[str] = []
        for path in paths:
            if (
                not path
                or len(path) > 500
                or path != path.strip()
                or not path.isprintable()
                or "\x00" in path
                or "\\" in path
                or "~" in path
                or any(character in path for character in "*?[")
            ):
                raise ValueError("sandbox paths must stay below /workspace")
            segments = path.split("/")
            if any(segment in {".", ".."} for segment in segments):
                raise ValueError("sandbox paths must stay below /workspace")
            normalized = posixpath.normpath(path)
            if normalized != "/workspace" and not normalized.startswith("/workspace/"):
                raise ValueError("sandbox paths must stay below /workspace")
            normalized_paths.append(normalized)
        return list(dict.fromkeys(normalized_paths))

    @field_validator("network_allowlist")
    @classmethod
    def validate_hosts(cls, hosts: list[str]) -> list[str]:
        normalized_hosts: list[str] = []
        for host in hosts:
            if (
                not host
                or len(host) > 253
                or host != host.strip()
                or host.endswith(".")
                or not re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*",
                    host,
                )
            ):
                raise ValueError("allowlist entries must be bare hostnames")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                if all(label.isdigit() for label in host.split(".")):
                    raise ValueError("allowlist entries must be bare hostnames") from None
            else:
                raise ValueError("allowlist entries must be bare hostnames")
            normalized_hosts.append(host.lower())
        return list(dict.fromkeys(normalized_hosts))

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, capabilities: list[str]) -> list[str]:
        for capability in capabilities:
            if (
                len(capability) > 80
                or not re.fullmatch(
                    r"[a-z0-9](?:[a-z0-9._-]{0,78}[a-z0-9])?", capability
                )
            ):
                raise ValueError("capabilities must use canonical lowercase names")
        return list(dict.fromkeys(capabilities))

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
        if self.correct_action != Action.SANDBOX and self.safe_blast_radius is not None:
            raise ValueError("only sandbox ground truth may define a safe blast radius")
        if any(not tell.strip() or len(tell) > 120 for tell in self.tells):
            raise ValueError("tells must be non-blank and at most 120 characters")
        if len(self.tells) != len(set(self.tells)):
            raise ValueError("tells must be unique")
        for tell, keywords in self.tell_keywords.items():
            if not tell.strip() or len(tell) > 120:
                raise ValueError("tell keyword names must be non-blank")
            if not keywords or len(keywords) > 24:
                raise ValueError("tell keyword groups must contain 1 to 24 keywords")
            if any(not keyword.strip() or len(keyword) > 120 for keyword in keywords):
                raise ValueError("tell keywords must be non-blank and at most 120 characters")
            if len(keywords) != len(set(keywords)):
                raise ValueError("tell keywords must be unique within each group")
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

    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    action: Action
    reasoning_text: str = Field(min_length=8, max_length=500)
    blast_radius_config: BlastRadiusConfig | None = None

    @field_validator("reasoning_text")
    @classmethod
    def normalize_reasoning(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 8:
            raise ValueError("reasoning must contain at least 8 non-padding characters")
        return normalized

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
    model_config = ConfigDict(extra="forbid")

    claim: str
    evidence: str
    source: str

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("receipt source must be an http(s) URL")
        return value


class PolicyDelta(BaseModel):
    dimension: str
    yours: str
    safe: str
    status: str = Field(pattern=r"^(ok|missing|excess)$")


class GradeVerification(BaseModel):
    """Public-input-only receipt for the gate that protected a graded round."""

    scenario_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    gate_passed: bool
    gate_reasons: list[str] = Field(default_factory=list)


class GradeResult(BaseModel):
    scenario_id: str
    family: str | None = None
    verdict: str = Field(pattern=r"^(correct|partial|wrong)$")
    action_correct: bool
    # The player's chosen action and the scenario's correct action, kept so the
    # results view can classify a wrong call as over-approval (too permissive) or
    # over-restriction (too cautious). Optional: rows persisted before this field
    # existed parse with None and are simply skipped by the oversight-bias tally.
    action: str | None = None
    correct_action: str | None = None
    reasoning_score: int = Field(ge=0, le=100)
    blast_radius_score: int | None = Field(default=None, ge=0, le=100)
    matched_tells: list[str]
    missed_tells: list[str]
    receipts: list[Receipt]
    explanation: str
    socratic_followup: str
    graded_by: str = "deterministic"
    critic_used: bool = False
    critic_model: str | None = None
    critic_response_id: str | None = None
    critic_effort: str | None = None
    critic_latency_ms: int | None = Field(default=None, ge=0)
    grading_degraded_reason: str | None = None
    deterministic_matched_tells: list[str] = Field(default_factory=list)
    critic_matched_tells: list[str] = Field(default_factory=list)
    safe_policy: BlastRadiusConfig | None = None
    policy_deltas: list[PolicyDelta] | None = None
    verification: GradeVerification | None = None


class CoachReply(BaseModel):
    feedback: str
    addressed_tell: str | None = None
    coached_by: str = "deterministic"


class TestQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    prompt: str = Field(min_length=10, max_length=500)
    options: list[str] = Field(min_length=2, max_length=5)
    correct_index: int = Field(ge=0)
    competency: Competency
    form: AssessmentForm

    @field_validator("options")
    @classmethod
    def options_are_distinct_and_nonblank(cls, options: list[str]) -> list[str]:
        if any(not option.strip() or len(option) > 300 for option in options):
            raise ValueError("question options must be non-blank and at most 300 characters")
        if len(options) != len(set(options)):
            raise ValueError("question options must be unique")
        return options

    @model_validator(mode="after")
    def correct_index_is_available(self) -> "TestQuestion":
        if self.correct_index >= len(self.options):
            raise ValueError("correct_index must reference an available option")
        return self

    def public_view(self) -> dict[str, Any]:
        return self.model_dump(exclude={"correct_index", "form"})


class SessionState(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: str = Field(pattern=r"^(demo|live|drill)$")
    operator_handle: str | None = None
    pretest_answers: list[int] | None = None
    pretest_score: int | None = None
    pretest_competency: dict[str, dict[str, int]] = Field(default_factory=dict)
    posttest_answers: list[int] | None = None
    posttest_score: int | None = None
    posttest_competency: dict[str, dict[str, int]] = Field(default_factory=dict)
    finished_early: bool = False
    scenario_order: list[str]
    current_index: int = 0
    active_scenario_id: str | None = None
    active_scenario_json: str | None = None
    active_anchor_id: str | None = None
    active_provenance: ScenarioProvenance | None = None
    active_generation_status: GenerationStatus | None = None
    last_gate_fallback_reason: str | None = None
    answered_scenario_ids: list[str] = Field(default_factory=list)
    reflected_scenario_ids: list[str] = Field(default_factory=list)
    shown_scenario_ids: list[str] = Field(default_factory=list)
    llm_calls_used: int = Field(default=0, ge=0)
    rounds_generated: int = Field(default=0, ge=0)
    grades: list[GradeResult] = Field(default_factory=list)
    competency: dict[str, dict[str, int]] = Field(default_factory=dict)
    # Original decisions for verified (bank) rounds so a coached retry can
    # re-grade revised reasoning with the action and sandbox policy held fixed.
    decision_log: dict[str, PlayerDecision] = Field(default_factory=dict)
    retried_grades: list[GradeResult] = Field(default_factory=list)


class CompetencyProgress(BaseModel):
    label: str
    hits: int = Field(ge=0)
    misses: int = Field(ge=0)
    mastery_percent: int = Field(ge=0, le=100)
    pre_score: int = Field(ge=0)
    pre_total: int = Field(ge=0)
    # Post-test fields are null when a session is finished early (never fabricated).
    post_score: int | None = Field(default=None, ge=0)
    post_total: int | None = Field(default=None, ge=0)
    test_delta: int | None = None


class RoundSummary(BaseModel):
    round: int = Field(ge=1)
    family: str
    verdict: str = Field(pattern=r"^(correct|partial|wrong)$")
    action_correct: bool
    reasoning_score: int = Field(ge=0, le=100)
    # Coached-retry outcome; null when the round was never revised. The baseline
    # is the initial grade's DETERMINISTIC coverage, so the before/after chip
    # compares like with like (the coached re-grade is deterministic-only).
    retried: bool = False
    retry_verdict: str | None = Field(default=None, pattern=r"^(correct|partial|wrong)$")
    retry_reasoning_score: int | None = Field(default=None, ge=0, le=100)
    retry_baseline_score: int | None = Field(default=None, ge=0, le=100)


class CompetencyRef(BaseModel):
    key: str
    label: str


class CompetencyDelta(BaseModel):
    key: str
    label: str
    delta: int


class OversightBias(BaseModel):
    """Which direction the player's wrong calls lean, over a finished session.

    Over-approval = allowing an action the correct call would have contained
    (the rubber-stamping failure this whole product is about). Over-restriction =
    blocking or over-constraining an action that was safer than the player treated
    it. Computed deterministically from the recorded action-vs-correct-action pairs;
    it is a directional tendency, not a precise score."""

    graded_rounds: int = Field(default=0, ge=0)
    correct: int = Field(default=0, ge=0)
    over_approval: int = Field(default=0, ge=0)
    over_restriction: int = Field(default=0, ge=0)
    dominant: str = Field(
        default="none", pattern=r"^(over_approval|over_restriction|balanced|none)$"
    )
    summary: str = ""


class LearnerProgress(BaseModel):
    session_id: str
    pretest_score: int
    posttest_score: int | None = None
    test_total: int
    delta: int | None = None
    finished_early: bool = False
    rounds_played: int
    rounds_generated: int
    competency_map: dict[Competency, CompetencyProgress]
    average_reasoning_score: int
    share_text: str
    rounds: list[RoundSummary] = Field(default_factory=list)
    weakest_competency: CompetencyRef | None = None
    rounds_needed_nudge: int = Field(default=0, ge=0)
    oversight_bias: OversightBias | None = None
    elapsed_seconds: int = Field(default=0, ge=0)
    strongest_gain: CompetencyDelta | None = None
    recommended_drill_family: str = ScenarioFamily.DANGEROUS_COMMAND.value


class DrillResult(BaseModel):
    """Compact summary returned with the decision grade of a one-round drill."""

    family: str
    competency: CompetencyRef
    verdict: str = Field(pattern=r"^(correct|partial|wrong)$")
    action_correct: bool
    reasoning_score: int = Field(ge=0, le=100)
    share_text: str


class SessionSummary(BaseModel):
    """Scores-only row persisted when a full session finishes.

    Deliberately carries no reasoning text, answers, or network identifiers —
    only aggregates plus the optional self-chosen operator handle. Summaries
    outlive the session TTL so the team board can aggregate finished runs."""

    session_id: str
    finished_at: datetime
    mode: str
    operator_handle: str | None = None
    pretest: int = Field(ge=0)
    posttest: int | None = Field(default=None, ge=0)
    delta: int | None = None
    rounds_played: int = Field(ge=0)
    rounds_generated: int = Field(ge=0)
    average_reasoning: int = Field(ge=0, le=100)
    families_cleared: int = Field(ge=0)
    weakest: str | None = None
    competency_json: str = "{}"
    finished_early: bool = False
    # Cumulative-scoring points for this run: correct=10, partial=4, wrong=1 over
    # the graded rounds. Defaults to 0 so rows persisted before this field existed
    # (NULL in SQLite) parse cleanly and contribute nothing to a user's total.
    score: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Persistent user identity + custom Blastling
# ---------------------------------------------------------------------------
# The pet is customised entirely from closed enum choices so it stays safe under
# the strict CSP: every option maps to a CSS class / data-attribute the frontend
# already ships, never to arbitrary markup or inline styles. The free-text name
# is reduced to a bounded slug before it is ever rendered.


class PetShape(StrEnum):
    CLOUD = "cloud"
    DROPLET = "droplet"
    ROCK = "rock"
    MONITOR = "monitor"


class PetPalette(StrEnum):
    CODEX = "codex"
    ACID = "acid"
    EMBER = "ember"
    VIOLET = "violet"
    SLATE = "slate"


class PetFace(StrEnum):
    TERMINAL = "terminal"
    DOT = "dot"
    VISOR = "visor"


class PetAccessory(StrEnum):
    NONE = "none"
    ANTENNA = "antenna"
    HALO = "halo"
    BOWTIE = "bowtie"
    SHADES = "shades"


class PetTrait(StrEnum):
    STOIC = "stoic"
    PLAYFUL = "playful"
    ANXIOUS = "anxious"
    PROUD = "proud"
    DEADPAN = "deadpan"


DEFAULT_PET_NAME = "fuse"


def slug_pet_name(raw: str | None) -> str:
    """Lowercase, collapse non-alphanumerics to '_', trim, cap at 24 chars.

    Mirrors the client-side slugForm() in pet.js so a name round-trips through
    the API unchanged. An empty result falls back to the default so the pet
    always has something to show."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower())
    slug = slug.strip("_")[:24]
    return slug or DEFAULT_PET_NAME


class PetConfig(BaseModel):
    """A user's custom Blastling. All visual axes are closed enums (CSP-safe);
    only the bounded, slugified name is free text."""

    model_config = ConfigDict(extra="forbid")

    shape: PetShape = PetShape.CLOUD
    palette: PetPalette = PetPalette.CODEX
    face: PetFace = PetFace.TERMINAL
    accessory: PetAccessory = PetAccessory.NONE
    trait: PetTrait = PetTrait.STOIC
    name: str = DEFAULT_PET_NAME

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, value: Any) -> str:
        return slug_pet_name(value)


# Nickname shares the operator-handle grammar so the two are interchangeable.
NICKNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$"


class UserProfile(BaseModel):
    """Public-facing profile for a persistent user, assembled on read. Carries no
    PII — the uid is an opaque per-browser token and the nickname is self-chosen."""

    uid: str
    nickname: str | None = None
    score: int = Field(default=0, ge=0)
    level: int = Field(default=1, ge=1)
    rank: int | None = Field(default=None, ge=1)
    sessions: int = Field(default=0, ge=0)
    best_delta: int | None = None
    families_cleared: int = Field(default=0, ge=0)
    pet: PetConfig = Field(default_factory=PetConfig)
    token_for_copy: str = ""


def level_for_score(score: int) -> int:
    """Cumulative level curve, shared verbatim with the pet's client-side curve
    (levelForXp in pet.js) so a user's profile level and pet level always agree."""
    return int((max(0, score) / 25) ** 0.5) + 1


INSPECTOR_DISCLAIMER = (
    "Deterministic keyword screen — no model ran. It flags known red-flag "
    "patterns; it cannot prove an artifact is safe. 'looks-scoped' means no "
    "known pattern matched."
)


class InspectionMatch(BaseModel):
    matched: str
    excerpt: str


class InspectionFinding(BaseModel):
    category: str
    label: str
    severity: str = Field(pattern=r"^(critical|caution)$")
    families: list[str]
    matches: list[InspectionMatch]
    # Additive, deterministic metadata (never affects the verdict).
    confidence: str = Field(default="", pattern=r"^(high|medium|low|)$")
    why: str | None = None
    fix: str | None = None


class InspectionProvenance(BaseModel):
    """Deterministic receipt for an inspection: enough to reproduce the verdict
    off any interpreter without trusting this instance. Echoes only public inputs
    (a fingerprint of the artifact the user submitted), never ground truth."""

    engine_version: str
    categories_hash: str
    input_fingerprint: str
    driving_findings: list[str] = Field(default_factory=list)
    # Count of embedded base64/hex payloads that were decoded and rescanned.
    decode_layers: int = Field(default=0, ge=0)
    # Fingerprint of any team custom-rule set applied (empty when none). Ties a
    # verdict to the exact rule set, so a receipt is reproducible with the same config.
    custom_rules_fingerprint: str = ""
    runtime: dict[str, str] = Field(default_factory=dict)


class InspectionReport(BaseModel):
    kind: str
    verdict: str = Field(pattern=r"^(reject-recommended|sandbox-recommended|looks-scoped)$")
    graded_by: str = "deterministic"
    method: str = "keyword-heuristic"
    disclaimer: str = INSPECTOR_DISCLAIMER
    findings: list[InspectionFinding] = Field(default_factory=list)
    families: list[dict[str, Any]] = Field(default_factory=list)
    parsed_as: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    baseline: str | None = Field(default=None, pattern=r"^(explicit|zero-trust)$")
    policy_deltas: list[PolicyDelta] | None = None
    learn: dict[str, str] | None = None
    toolkit: dict[str, str] | None = None
    provenance: InspectionProvenance | None = None
    confidence: str = Field(default="", pattern=r"^(high|medium|low|)$")
    correlations: list[dict[str, Any]] = Field(default_factory=list)


class CustomRule(BaseModel):
    """A team-authored detection rule, layered on top of the built-in screen. It
    can only ADD coverage — never relax it. Reuses the built-in category shape
    (id/label/severity/keywords/patterns) so it screens exactly like a shipped one."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,60}$")
    label: str = Field(min_length=3, max_length=100)
    severity: str = Field(default="caution", pattern=r"^(critical|caution)$")
    family: ScenarioFamily = ScenarioFamily.DANGEROUS_COMMAND
    keywords: list[str] = Field(default_factory=list, max_length=24)
    patterns: list[str] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def has_a_matcher(self) -> "CustomRule":
        if not self.keywords and not self.patterns:
            raise ValueError("a custom rule needs at least one keyword or pattern")
        if any(len(keyword) > 120 or not keyword.strip() for keyword in self.keywords):
            raise ValueError("custom keywords must be non-blank and at most 120 characters")
        for pattern in self.patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"invalid custom pattern {pattern!r}: {error}") from None
        return self


class CustomRulesConfig(BaseModel):
    """A repo's `.blastradius.toml`: extra rules plus a caution-only allowlist.

    Honesty is enforced by construction — there is no field that can suppress a
    built-in critical finding. `allowlist` regexes only ever drop *caution* noise
    (built-in or custom); criticals always survive to the verdict."""

    model_config = ConfigDict(extra="forbid")

    rules: list[CustomRule] = Field(default_factory=list, max_length=64)
    allowlist: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_config(self) -> "CustomRulesConfig":
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("custom rule ids must be unique")
        for pattern in self.allowlist:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"invalid allowlist pattern {pattern!r}: {error}") from None
        return self
