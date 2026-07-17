import asyncio
import hashlib
import json
import logging
import time
from collections import deque
from datetime import UTC, datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from blast_radius.auth import ACCESS_COOKIE, verify_token
from blast_radius.config import Settings
from blast_radius.engine import TrustEngine, inspector
from blast_radius.engine.openai_adapter import SessionLLMBudget
from blast_radius.models import (
    COMPETENCY_LABELS,
    AssessmentForm,
    BlastRadiusConfig,
    CoachReply,
    Competency,
    CompetencyProgress,
    CompetencyRef,
    DrillResult,
    GateResult,
    GenerationStatus,
    InspectionReport,
    LearnerProgress,
    PlayerDecision,
    RoundSummary,
    Scenario,
    ScenarioFamily,
    SessionState,
    SessionSummary,
    ScenarioProvenance,
    competency_for_family,
)
from blast_radius.storage import SessionStore


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(default="demo", pattern=r"^(demo|live|drill)$")
    family: str | None = None
    client_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$")
    operator_handle: str | None = Field(
        default=None,
        min_length=2,
        max_length=40,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$",
    )

    @field_validator("family")
    @classmethod
    def family_is_known(cls, value: str | None) -> str | None:
        if value is not None:
            ScenarioFamily(value)  # raises ValueError -> 422 for unknown families
        return value

    @model_validator(mode="after")
    def drill_only_fields(self) -> "CreateSessionRequest":
        if self.mode != "drill" and (self.family or self.client_key):
            raise ValueError("family and client_key are drill-mode options")
        return self


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["command", "diff", "config"]
    content: str | None = Field(default=None, max_length=64_000)
    config: BlastRadiusConfig | None = None
    expected: BlastRadiusConfig | None = None

    @model_validator(mode="after")
    def shape_matches_kind(self) -> "CheckRequest":
        if self.kind == "config":
            if self.config is None:
                raise ValueError("kind 'config' requires a config object")
            if self.content is not None:
                raise ValueError("kind 'config' does not take content")
        else:
            if self.content is None:
                raise ValueError(f"kind '{self.kind}' requires content")
            if self.config is not None or self.expected is not None:
                raise ValueError("config and expected are only valid for kind 'config'")
            if self.kind == "command" and len(self.content) > 8_000:
                raise ValueError("command content must be at most 8000 characters")
        return self


class GateVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Scenario


class TestAnswersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[int] = Field(min_length=1, max_length=100)


class ReflectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    question: str = Field(min_length=8, max_length=500)


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    reasoning_text: str = Field(min_length=8, max_length=500)


logger = logging.getLogger(__name__)


def _deterministic_coverage(grade) -> int:
    """The deterministic-only tell coverage of a grade, so a coached (always
    deterministic) re-grade compares like-with-like against an initial grade the
    live critic may have boosted."""
    total = len(grade.matched_tells) + len(grade.missed_tells)
    if not total:
        return 0
    return round(100 * len(grade.deterministic_matched_tells) / total)


def assessment_option_order(
    session_id: str,
    form: AssessmentForm,
    question_id: str,
    option_count: int,
) -> list[int]:
    """Return a stable, session-specific option order without exposing the answer."""
    order = sorted(
        range(option_count),
        key=lambda index: hashlib.sha256(
            (
                "blast-radius-assessment:v1:"
                f"{session_id}:{form.value}:{question_id}:{index}"
            ).encode()
        ).digest(),
    )
    if option_count > 1 and order == list(range(option_count)):
        digest = hashlib.sha256(
            f"blast-radius-assessment:v1:{session_id}:{form.value}:{question_id}".encode()
        ).digest()
        offset = 1 + digest[0] % (option_count - 1)
        order = order[offset:] + order[:offset]
    return order


@dataclass
class _SessionLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class SessionMutationLocks:
    """Serialize mutations per session without retaining idle session IDs."""

    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._entries: dict[str, _SessionLockEntry] = {}

    @property
    def active_key_count(self) -> int:
        return len(self._entries)

    @asynccontextmanager
    async def hold(self, session_id: str) -> AsyncIterator[None]:
        async with self._guard:
            entry = self._entries.setdefault(session_id, _SessionLockEntry())
            entry.users += 1
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            async with self._guard:
                entry.users -= 1
                if entry.users == 0 and self._entries.get(session_id) is entry:
                    self._entries.pop(session_id, None)


class SlidingWindowLimiter:
    def __init__(self, limit: int = 45, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            bucket = self.hits.setdefault(key, deque())
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests; pause and try again.",
                )
            bucket.append(now)


def _load_content_list(path: Path) -> list[dict]:
    """Load a read-only content file (learn/toolkit) as a validated JSON list."""
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path.name} must contain a non-empty JSON list")
    return value


def build_router(settings: Settings, engine: TrustEngine, store: SessionStore) -> APIRouter:
    router = APIRouter(prefix="/api")
    limiter = SlidingWindowLimiter()
    session_create_limiter = SlidingWindowLimiter(
        limit=settings.session_create_limit_per_hour,
        window_seconds=60 * 60,
    )
    round_ip_limiter = SlidingWindowLimiter(
        limit=settings.round_request_limit_per_minute,
        window_seconds=60,
    )
    round_session_limiter = SlidingWindowLimiter(
        limit=settings.session_round_request_cap,
        window_seconds=settings.session_ttl_minutes * 60,
    )
    check_limiter = SlidingWindowLimiter(
        limit=settings.check_limit_per_minute, window_seconds=60
    )
    gate_verify_limiter = SlidingWindowLimiter(
        limit=settings.gate_verify_limit_per_minute, window_seconds=60
    )
    team_summary_limiter = SlidingWindowLimiter(
        limit=settings.team_summary_limit_per_minute, window_seconds=60
    )
    session_mutations = SessionMutationLocks()

    learn_modules = _load_content_list(engine.bank.data_dir / "learn.json")
    toolkit_cards = _load_content_list(engine.bank.data_dir / "toolkit.json")
    learn_by_family = {card["family"]: card for card in learn_modules if "family" in card}
    toolkit_by_family = {card["family"]: card for card in toolkit_cards if "family" in card}
    bank_fingerprints = inspector.bank_artifact_fingerprints(engine.bank)

    def client_host(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def request_role(request: Request) -> str | None:
        """Resolve the access-cookie role inside a router handler (no coupling to
        the app middleware). Returns None when the cookie is absent or invalid."""
        return verify_token(
            settings.auth_secret,
            request.cookies.get(ACCESS_COOKIE),
            max_age_seconds=settings.auth_cookie_ttl_days * 86400,
        )

    def require_developer(request: Request) -> None:
        # When the gate is off (local dev, tests) everything is open, matching the
        # rest of the app; when on, only the developer role may reach team views.
        if not settings.auth_enabled:
            return
        if request_role(request) != "developer":
            raise HTTPException(status_code=403, detail="Developer access required.")

    def limit_round_request(request: Request, session_id: str) -> None:
        round_ip_limiter.check(f"round-ip:{client_host(request)}")
        round_session_limiter.check(f"round-session:{session_id}")

    def load_session(session_id: str, request: Request) -> SessionState:
        state = store.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found or expired.")
        limiter.check(f"{client_host(request)}:{session_id}")
        return state

    def reload_session(session_id: str) -> SessionState:
        state = store.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found or expired.")
        return state

    SessionDep = Annotated[SessionState, Depends(load_session)]

    # Rank by family, not scenario id: every demo deck is one scenario per family
    # (canonical or per-session seeded), so the adaptive reorder needs a stable
    # tiebreak that is defined for whichever member a session happened to draw.
    demo_family_rank = {
        engine.bank.get(scenario_id).family: index
        for index, scenario_id in enumerate(engine.bank.demo_order())
    }

    def assessment_view(session_id: str, form: AssessmentForm) -> list[dict]:
        result = []
        for question in engine.bank.questions_for(form):
            order = assessment_option_order(
                session_id,
                form,
                question.id,
                len(question.options),
            )
            public = question.public_view()
            public["options"] = [question.options[index] for index in order]
            result.append(public)
        return result

    def score_test(
        session_id: str,
        form: AssessmentForm,
        answers: list[int],
    ) -> tuple[int, dict[str, dict[str, int]]]:
        questions = engine.bank.questions_for(form)
        if len(answers) != len(questions):
            raise HTTPException(
                status_code=422,
                detail=f"Exactly {len(questions)} answers are required.",
            )
        competency_scores = {
            competency.value: {"score": 0, "total": 0} for competency in Competency
        }
        for question, answer in zip(questions, answers, strict=True):
            if answer < 0 or answer >= len(question.options):
                raise HTTPException(status_code=422, detail="An answer index is out of range.")
            order = assessment_option_order(
                session_id,
                form,
                question.id,
                len(question.options),
            )
            record = competency_scores[question.competency.value]
            record["total"] += 1
            record["score"] += int(order[answer] == question.correct_index)
        return sum(record["score"] for record in competency_scores.values()), competency_scores

    def competency_accuracy(state: SessionState, competency: Competency) -> float:
        test_record = state.pretest_competency.get(
            competency.value, {"score": 0, "total": 0}
        )
        round_record = state.competency.get(
            competency.value, {"hits": 0, "misses": 0}
        )
        hits = test_record.get("score", 0) + round_record.get("hits", 0)
        total = (
            test_record.get("total", 0)
            + round_record.get("hits", 0)
            + round_record.get("misses", 0)
        )
        return hits / total if total else 1.0

    def summarize(state: SessionState) -> SessionSummary:
        """Build a scores-only durable summary of a finished session. Carries no
        reasoning text, answers, or IPs — only aggregates and the optional handle."""
        average = (
            round(sum(grade.reasoning_score for grade in state.grades) / len(state.grades))
            if state.grades
            else 0
        )
        finished_early = state.posttest_score is None
        delta = None if finished_early else state.posttest_score - (state.pretest_score or 0)
        weakest = min(Competency, key=lambda item: competency_accuracy(state, item))
        families_cleared = len(
            {grade.family for grade in state.grades if grade.action_correct and grade.family}
        )
        return SessionSummary(
            session_id=state.id,
            finished_at=datetime.now(UTC),
            mode=state.mode,
            operator_handle=state.operator_handle,
            pretest=state.pretest_score or 0,
            posttest=state.posttest_score,
            delta=delta,
            rounds_played=len(state.grades),
            rounds_generated=state.rounds_generated,
            average_reasoning=average,
            families_cleared=families_cleared,
            weakest=weakest.value,
            competency_json=json.dumps(state.competency),
            finished_early=finished_early,
        )

    def reorder_demo_suffix(state: SessionState, start: int) -> None:
        if state.mode != "demo":
            return
        remaining = state.scenario_order[start:]
        remaining.sort(
            key=lambda scenario_id: (
                competency_accuracy(
                    state,
                    competency_for_family(engine.bank.get(scenario_id).family),
                ),
                demo_family_rank[engine.bank.get(scenario_id).family],
            )
        )
        state.scenario_order[start:] = remaining

    def live_generation_availability(state: SessionState | None = None) -> tuple[bool, str]:
        available, reason = engine.live_generation_availability(
            store.budget_remaining(settings.daily_llm_budget)
        )
        if state is not None:
            remaining_rounds = len(state.scenario_order) - state.current_index
            # One generation attempt costs up to 2 calls; every remaining round
            # keeps one reserved grading call, so generation can never starve
            # the live critic for the rest of the session.
            if state.llm_calls_used + 2 + remaining_rounds > settings.session_llm_call_cap:
                return False, "grading_reserved"
            if state.rounds_generated >= settings.generated_rounds_per_session:
                return False, "round_cap"
        return available, reason

    @router.get("/demo/gate-catch")
    def demo_gate_catch(request: Request, case: str = "tell") -> dict:
        limiter.check(f"gate-catch:{client_host(request)}")
        if case not in {"tell", "citation"}:
            raise HTTPException(status_code=422, detail="case must be tell or citation")
        planted = engine.bank.get("dep-typo-1").model_copy(deep=True)
        planted.id = "demo-planted-hallucination"
        if case == "tell":
            planted_claim = "hidden remote code execution backdoor"
            planted.ground_truth.tells.append(planted_claim)
            planted.ground_truth.tell_keywords[planted_claim] = [
                "remote code execution",
                "backdoor",
            ]
        else:
            planted_claim = "off-catalog security receipt"
            planted.ground_truth.evidence[0].source = (
                "https://example.com/fabricated-security-guidance"
            )
        result = engine.gate.verify(planted)
        return {
            "case": case,
            "planted_claim": planted_claim,
            "passed": result.passed,
            "reasons": result.reasons,
        }

    @router.get("/learn")
    def learn(request: Request) -> dict:
        limiter.check(f"learn:{client_host(request)}")
        return {"modules": learn_modules}

    @router.get("/toolkit")
    def toolkit(request: Request) -> dict:
        limiter.check(f"toolkit:{client_host(request)}")
        return {"cards": toolkit_cards}

    def _attach_resources(report: InspectionReport) -> None:
        if not report.families:
            return
        top_family = report.families[0]["family"]
        learn_card = learn_by_family.get(top_family)
        toolkit_card = toolkit_by_family.get(top_family)
        if learn_card:
            report.learn = {"family": top_family, "title": learn_card.get("title", "")}
        if toolkit_card:
            report.toolkit = {"family": top_family, "title": toolkit_card.get("title", "")}

    @router.post("/check", response_model=InspectionReport)
    def check_artifact(payload: CheckRequest, request: Request) -> InspectionReport:
        """Deterministic red-flag screen for a real command/diff/sandbox config.

        No model runs; the response is honest about being a keyword heuristic.
        A curated drill artifact is refused so this cannot leak a live round's
        verdict."""
        check_limiter.check(f"check:{client_host(request)}")
        if payload.kind == "config":
            report = inspector.inspect_config(payload.config, payload.expected)
        else:
            if bank_fingerprints & inspector.guard_fingerprints(payload.content, payload.kind):
                raise HTTPException(
                    status_code=422,
                    detail="This artifact is a Blast Radius drill scenario — "
                    "decide it in a session instead.",
                )
            report = inspector.inspect_text(payload.content, kind=payload.kind)
        _attach_resources(report)
        return report

    @router.post("/gate/verify", response_model=GateResult)
    def gate_verify(payload: GateVerifyRequest, request: Request) -> GateResult:
        """Run the production CorrectnessGate against an author's draft scenario.

        Developer-role only, matching the /author page it backs. The draft carries
        its own ground truth (the author's); the gate's reasons only ever quote the
        submitted draft, never a curated scenario's ground truth. (There is no
        trusted-base comparison here — that path would echo curated tell names.)"""
        require_developer(request)
        gate_verify_limiter.check(f"gate-verify:{client_host(request)}")
        return engine.gate.verify(payload.scenario)

    @router.get("/team/summary")
    def team_summary(request: Request) -> dict:
        """Aggregate finished-session summaries for the developer-only team board.

        Rows carry scores only (no reasoning text, answers, or IPs). Anonymous
        sessions collapse into an 'anonymous' roster entry."""
        require_developer(request)
        team_summary_limiter.check(f"team:{client_host(request)}")
        summaries = store.list_summaries()
        roster: dict[str, dict] = {}
        for summary in summaries:
            handle = summary.operator_handle or "anonymous"
            entry = roster.setdefault(
                handle,
                {
                    "handle": handle,
                    "sessions": 0,
                    "best_delta": None,
                    "latest_finished_at": None,
                    "weakest": None,
                    "families_cleared": 0,
                    "average_reasoning": 0,
                    "_reasoning_total": 0,
                },
            )
            entry["sessions"] += 1
            entry["_reasoning_total"] += summary.average_reasoning
            entry["families_cleared"] = max(entry["families_cleared"], summary.families_cleared)
            if summary.delta is not None and (
                entry["best_delta"] is None or summary.delta > entry["best_delta"]
            ):
                entry["best_delta"] = summary.delta
            finished_at = summary.finished_at.isoformat()
            if entry["latest_finished_at"] is None or finished_at > entry["latest_finished_at"]:
                entry["latest_finished_at"] = finished_at
                entry["weakest"] = summary.weakest
        roster_rows = []
        for entry in roster.values():
            reasoning_total = entry.pop("_reasoning_total")
            entry["average_reasoning"] = (
                round(reasoning_total / entry["sessions"]) if entry["sessions"] else 0
            )
            roster_rows.append(entry)
        roster_rows.sort(key=lambda row: (-row["sessions"], row["handle"]))
        return {
            "summaries": [summary.model_dump(mode="json") for summary in summaries],
            "roster": roster_rows,
            "window": "all finished sessions (summaries persist beyond the "
            "180-minute session TTL)",
        }

    @router.post("/sessions", status_code=status.HTTP_201_CREATED)
    def create_session(payload: CreateSessionRequest, request: Request) -> dict:
        session_create_limiter.check(f"session-create:{client_host(request)}")
        session_id = str(uuid4())
        if payload.mode == "drill":
            # One bank round, no assessments; seeded per-day per-client so a
            # returning browser gets a stable scenario within a day. The client
            # key is used only to pick and is never stored on the session.
            family = ScenarioFamily(payload.family) if payload.family else None
            day = datetime.now(UTC).date().isoformat()
            scenario = engine.bank.drill_pick(
                day=day,
                client_key=payload.client_key or session_id,
                family=family,
            )
            scenario_order = [scenario.id]
        else:
            scenario_order = engine.bank.demo_order(seed=session_id)
        state = SessionState(
            id=session_id,
            mode=payload.mode,
            operator_handle=payload.operator_handle,
            scenario_order=scenario_order,
        )
        store.save(state)
        generation_available, _ = live_generation_availability()
        return {
            "session_id": state.id,
            "mode": state.mode,
            "operator_handle": state.operator_handle,
            "rounds_total": len(state.scenario_order),
            "pretest": [] if state.mode == "drill" else assessment_view(state.id, AssessmentForm.PRE),
            "live_generation_available": generation_available,
            "reasoning_grading": engine.openai.reasoning_grading_state,
        }

    @router.post("/sessions/{session_id}/pretest")
    async def submit_pretest(
        session_id: str,
        request: Request,
        payload: TestAnswersRequest,
    ) -> dict:
        load_session(session_id, request)
        async with session_mutations.hold(session_id):
            state = reload_session(session_id)
            if state.mode == "drill":
                raise HTTPException(
                    status_code=409, detail="Drill sessions do not include assessments."
                )
            if state.pretest_answers is not None:
                raise HTTPException(status_code=409, detail="Pre-test was already submitted.")
            state.pretest_answers = payload.answers
            state.pretest_score, state.pretest_competency = score_test(
                state.id,
                AssessmentForm.PRE,
                payload.answers,
            )
            reorder_demo_suffix(state, 0)
            store.save(state)
            return {
                "score": state.pretest_score,
                "total": engine.bank.assessment_size,
            }

    async def next_round_locked(
        session_id: str,
        request: Request,
        state: SessionState,
    ) -> dict:
        if state.mode != "drill" and state.pretest_score is None:
            raise HTTPException(status_code=409, detail="Complete the pre-test first.")
        if state.posttest_score is not None or state.finished_early:
            raise HTTPException(status_code=409, detail="This session is complete.")
        if state.current_index >= len(state.scenario_order):
            if state.mode == "drill":
                return {"complete": True, "drill_complete": True}
            return {
                "complete": True,
                "posttest": assessment_view(state.id, AssessmentForm.POST),
            }
        is_new_active = not bool(state.active_scenario_json)
        # Idempotent replays of the active round are free; only a fresh round
        # consumes the per-IP and per-session caps, so client retries can never
        # rate-limit a session out of its own game.
        if is_new_active:
            limit_round_request(request, session_id)
        if state.active_scenario_json:
            scenario = Scenario.model_validate_json(state.active_scenario_json)
            anchor_id = state.active_anchor_id or scenario.id
            provenance = state.active_provenance or ScenarioProvenance.VERIFIED
            generation_status = (
                state.active_generation_status or GenerationStatus.NOT_REQUESTED
            )
        elif state.mode in {"demo", "drill"}:
            scenario = engine.bank.get(state.scenario_order[state.current_index])
            anchor_id = scenario.id
            provenance = ScenarioProvenance.VERIFIED
            generation_status = GenerationStatus.NOT_REQUESTED
            gate = engine.gate.verify(scenario)
            if not gate.passed:
                rejected_id = scenario.id
                rejected_family = scenario.family
                rejection_reasons = list(gate.reasons)
                excluded = set(state.answered_scenario_ids) | {rejected_id}
                scenario = None
                for attempt in range(len(engine.bank.scenarios)):
                    try:
                        candidate = engine.bank.fallback(
                            family=rejected_family,
                            exclude=excluded,
                            seed=f"{state.id}:{state.current_index}:{attempt}",
                        )
                    except LookupError:
                        break
                    if candidate.family != rejected_family:
                        break
                    candidate_gate = engine.gate.verify(candidate)
                    if candidate_gate.passed:
                        scenario = candidate
                        break
                    excluded.add(candidate.id)
                if scenario is None:
                    logger.error(
                        "No verified demo fallback for scenario=%s reasons=%s",
                        rejected_id,
                        rejection_reasons,
                    )
                    raise HTTPException(
                        status_code=503, detail="No verified scenario is currently available."
                    )
                state.last_gate_fallback_reason = "; ".join(rejection_reasons)
                logger.warning(
                    "Replaced gate-failing demo scenario=%s with fallback=%s reasons=%s",
                    rejected_id,
                    scenario.id,
                    rejection_reasons,
                )
                anchor_id = scenario.id
                generation_status = GenerationStatus.FELL_BACK
        else:
            target = engine.bank.get(state.scenario_order[state.current_index])
            weakest = min(Competency, key=lambda item: competency_accuracy(state, item)).value
            difficulty = min(5, 1 + state.current_index)
            generation_available, unavailable_reason = live_generation_availability(state)
            session_budget = SessionLLMBudget(
                limit=settings.session_llm_call_cap,
                used=state.llm_calls_used,
            )
            selection = await engine.next_scenario(
                family=target.family,
                difficulty=difficulty,
                blind_spot=weakest,
                exclude=set(state.shown_scenario_ids),
                seed=f"{state.id}:{state.current_index}",
                safety_identifier=state.id,
                generation_requested=True,
                generation_available=generation_available,
                generation_unavailable_reason=unavailable_reason,
                session_budget=session_budget,
            )
            state.llm_calls_used = session_budget.used
            scenario = selection.scenario
            anchor_id = selection.anchor_id
            provenance = selection.provenance
            generation_status = selection.generation_status
            state.last_gate_fallback_reason = selection.failure_reason
        if is_new_active:
            state.active_scenario_id = scenario.id
            state.active_scenario_json = scenario.model_dump_json()
            state.active_anchor_id = anchor_id
            state.active_provenance = provenance
            state.active_generation_status = generation_status
            for shown_id in (anchor_id, scenario.id):
                if shown_id not in state.shown_scenario_ids:
                    state.shown_scenario_ids.append(shown_id)
            if provenance == ScenarioProvenance.GENERATED:
                state.rounds_generated += 1
            store.save(state)
        # After round 1 the demo deck has been reordered to lead with the player's
        # weakest area; name it so the adaptive reorder is visible, not silent.
        adaptive_focus = None
        if state.mode == "demo" and state.current_index >= 1:
            weakest = min(Competency, key=lambda item: competency_accuracy(state, item))
            adaptive_focus = COMPETENCY_LABELS[weakest]
        return {
            "complete": False,
            "round_number": state.current_index + 1,
            "rounds_total": len(state.scenario_order),
            "seconds": 90 if state.mode == "drill" else max(35, 70 - state.current_index * 5),
            "provenance": provenance,
            "generation_status": generation_status,
            "adaptive_focus": adaptive_focus,
            "scenario": scenario.public_view(),
        }

    @router.post("/sessions/{session_id}/rounds/next")
    async def next_round(session_id: str, request: Request) -> dict:
        load_session(session_id, request)
        async with session_mutations.hold(session_id):
            return await next_round_locked(
                session_id,
                request,
                reload_session(session_id),
            )

    async def submit_decision_locked(
        session_id: str,
        request: Request,
        decision: PlayerDecision,
        state: SessionState,
    ) -> dict:
        if state.finished_early:
            raise HTTPException(status_code=409, detail="This session was finished early.")
        limit_round_request(request, session_id)
        # Duplicate check runs first: after a processed decision the active slot is
        # cleared, so a client retry must hear the truth, not "request a round".
        if decision.scenario_id in state.answered_scenario_ids:
            raise HTTPException(status_code=409, detail="This round was already answered.")
        if not state.active_scenario_json or not state.active_scenario_id:
            raise HTTPException(status_code=409, detail="Request a round before answering.")
        if decision.scenario_id != state.active_scenario_id:
            raise HTTPException(status_code=409, detail="Decision does not match the active round.")
        scenario = Scenario.model_validate_json(state.active_scenario_json)
        session_budget = SessionLLMBudget(
            limit=settings.session_llm_call_cap,
            used=state.llm_calls_used,
        )
        grade = await engine.grade(
            scenario,
            decision,
            safety_identifier=state.id,
            allow_critic=state.active_provenance != ScenarioProvenance.GENERATED,
            session_budget=session_budget,
        )
        state.llm_calls_used = session_budget.used
        competency = competency_for_family(scenario.family).value
        record = state.competency.setdefault(competency, {"hits": 0, "misses": 0})
        for tell in scenario.ground_truth.tells:
            record["hits" if tell in grade.matched_tells else "misses"] += 1
        state.grades.append(grade)
        state.answered_scenario_ids.append(scenario.id)
        # Persist the decision for verified (bank) rounds so a coached retry can
        # re-grade revised reasoning with the action and policy held fixed.
        # Generated rounds are never retried (their ground truth is discarded).
        if scenario.id in engine.bank.scenarios:
            state.decision_log[scenario.id] = decision
        state.current_index += 1
        state.active_scenario_id = None
        state.active_scenario_json = None
        state.active_anchor_id = None
        state.active_provenance = None
        state.active_generation_status = None
        reorder_demo_suffix(state, state.current_index)
        store.save(state)
        response = {
            "grade": grade.model_dump(mode="json"),
            "rounds_remaining": len(state.scenario_order) - state.current_index,
        }
        if state.mode == "drill":
            competency_ref = competency_for_family(scenario.family)
            family_words = scenario.family.value.replace("_", " ")
            response["drill"] = DrillResult(
                family=scenario.family.value,
                competency=CompetencyRef(
                    key=competency_ref.value, label=COMPETENCY_LABELS[competency_ref]
                ),
                verdict=grade.verdict,
                action_correct=grade.action_correct,
                reasoning_score=grade.reasoning_score,
                share_text=(
                    f"Daily Blast Radius drill: {family_words} — {grade.verdict}, "
                    f"{grade.reasoning_score}% tell coverage."
                ),
            ).model_dump(mode="json")
        return response

    @router.post("/sessions/{session_id}/decisions")
    async def submit_decision(
        session_id: str,
        request: Request,
        decision: PlayerDecision,
    ) -> dict:
        load_session(session_id, request)
        async with session_mutations.hold(session_id):
            return await submit_decision_locked(
                session_id,
                request,
                decision,
                reload_session(session_id),
            )

    @router.post("/sessions/{session_id}/rounds/reflect", response_model=CoachReply)
    async def reflect_on_round(
        session_id: str,
        request: Request,
        payload: ReflectRequest,
    ) -> CoachReply:
        load_session(session_id, request)
        async with session_mutations.hold(session_id):
            state = reload_session(session_id)
            # Coaching is bank-only: generated live-* ground truth is discarded at submit.
            if payload.scenario_id not in engine.bank.scenarios:
                raise HTTPException(
                    status_code=409,
                    detail="Reflection is available for verified rounds only.",
                )
            grade = next(
                (
                    result
                    for result in reversed(state.grades)
                    if result.scenario_id == payload.scenario_id
                ),
                None,
            )
            if grade is None:
                raise HTTPException(
                    status_code=409, detail="Answer this round before reflecting on it."
                )
            if payload.scenario_id in state.reflected_scenario_ids:
                raise HTTPException(
                    status_code=409,
                    detail="You have already used this round's reflection.",
                )
            # Reserve one grading call per remaining round so the optional coach can
            # never starve the critic; if the floor would break, coach deterministically.
            remaining_rounds = len(state.scenario_order) - state.current_index
            floor_ok = (
                state.llm_calls_used + 1 + remaining_rounds <= settings.session_llm_call_cap
            )
            session_budget = SessionLLMBudget(
                limit=settings.session_llm_call_cap if floor_ok else 0,
                used=state.llm_calls_used if floor_ok else 0,
            )
            reply = await engine.coach(
                engine.bank.get(payload.scenario_id),
                grade.matched_tells,
                grade.missed_tells,
                payload.question,
                safety_identifier=state.id,
                session_budget=session_budget,
            )
            if floor_ok:
                state.llm_calls_used = session_budget.used
            state.reflected_scenario_ids.append(payload.scenario_id)
            store.save(state)
            return reply

    @router.post("/sessions/{session_id}/rounds/retry")
    async def retry_round(
        session_id: str,
        request: Request,
        payload: RetryRequest,
    ) -> dict:
        load_session(session_id, request)
        async with session_mutations.hold(session_id):
            state = reload_session(session_id)
            if state.mode == "drill":
                raise HTTPException(
                    status_code=409, detail="Drill sessions do not include coached retries."
                )
            if state.posttest_score is not None or state.finished_early:
                raise HTTPException(status_code=409, detail="This session is complete.")
            if payload.scenario_id not in engine.bank.scenarios:
                raise HTTPException(
                    status_code=409, detail="Revision is available for verified rounds only."
                )
            initial = next(
                (
                    grade
                    for grade in reversed(state.grades)
                    if grade.scenario_id == payload.scenario_id
                ),
                None,
            )
            if initial is None:
                raise HTTPException(
                    status_code=409, detail="Answer this round before revising."
                )
            if initial.verdict == "correct":
                raise HTTPException(
                    status_code=409, detail="Only partial or wrong rounds can be revised."
                )
            if any(g.scenario_id == payload.scenario_id for g in state.retried_grades):
                raise HTTPException(
                    status_code=409, detail="You have already used this round's revision."
                )
            original = state.decision_log.get(payload.scenario_id)
            if original is None:
                raise HTTPException(
                    status_code=409, detail="Revision is unavailable for this round."
                )
            # Action and sandbox policy stay fixed; only the reasoning is revised.
            # Deterministic-only (no critic) keeps the reflect budget floor intact.
            revised = PlayerDecision(
                scenario_id=original.scenario_id,
                action=original.action,
                reasoning_text=payload.reasoning_text,
                blast_radius_config=original.blast_radius_config,
            )
            scenario = engine.bank.get(payload.scenario_id)
            coached = await engine.grade(
                scenario,
                revised,
                safety_identifier=state.id,
                allow_critic=False,
            )
            state.retried_grades.append(coached)
            store.save(state)
            # Compare deterministic-to-deterministic: the coached grade never
            # ran the critic, so basing "improved" on the (possibly critic-
            # boosted) initial reasoning_score would misreport a real gain.
            initial_deterministic = _deterministic_coverage(initial)
            return {
                "initial": initial.model_dump(mode="json"),
                "coached": coached.model_dump(mode="json"),
                "initial_deterministic_score": initial_deterministic,
                "improved": coached.reasoning_score > initial_deterministic,
            }

    @router.post("/sessions/{session_id}/posttest")
    async def submit_posttest(
        session_id: str,
        request: Request,
        payload: TestAnswersRequest,
    ) -> dict:
        load_session(session_id, request)
        async with session_mutations.hold(session_id):
            state = reload_session(session_id)
            if state.mode == "drill":
                raise HTTPException(
                    status_code=409, detail="Drill sessions do not include assessments."
                )
            if state.finished_early:
                raise HTTPException(
                    status_code=409, detail="This session was finished early."
                )
            if state.current_index < len(state.scenario_order) or state.active_scenario_id:
                raise HTTPException(
                    status_code=409, detail="Finish all rounds before the post-test."
                )
            if state.posttest_answers is not None:
                raise HTTPException(status_code=409, detail="Post-test was already submitted.")
            state.posttest_answers = payload.answers
            state.posttest_score, state.posttest_competency = score_test(
                state.id,
                AssessmentForm.POST,
                payload.answers,
            )
            store.save(state)
            store.record_summary(summarize(state))
            return {
                "score": state.posttest_score,
                "total": engine.bank.assessment_size,
            }

    @router.post("/sessions/{session_id}/finish-early")
    async def finish_early(session_id: str, request: Request) -> dict:
        load_session(session_id, request)
        async with session_mutations.hold(session_id):
            state = reload_session(session_id)
            if state.pretest_score is None:
                raise HTTPException(status_code=409, detail="Complete the pre-test first.")
            if state.posttest_score is not None:
                raise HTTPException(
                    status_code=409, detail="This session is already complete."
                )
            if not state.grades:
                raise HTTPException(
                    status_code=409,
                    detail="Play at least one round before finishing early.",
                )
            state.finished_early = True
            # Drop any in-flight round so results reflect only answered rounds.
            state.active_scenario_id = None
            state.active_scenario_json = None
            state.active_anchor_id = None
            state.active_provenance = None
            state.active_generation_status = None
            store.save(state)
            store.record_summary(summarize(state))
            return {"finished_early": True, "rounds_played": len(state.grades)}

    @router.get("/sessions/{session_id}/results", response_model=LearnerProgress)
    def results(state: SessionDep) -> LearnerProgress:
        if state.pretest_score is None:
            raise HTTPException(status_code=409, detail="Complete the session to view results.")
        finished_early = state.posttest_score is None
        if finished_early and not state.finished_early:
            raise HTTPException(status_code=409, detail="Complete the session to view results.")
        average = (
            round(sum(grade.reasoning_score for grade in state.grades) / len(state.grades))
            if state.grades
            else 0
        )
        # A finished-early session never took the post-test, so the delta is not
        # measured — report it null rather than fabricate a number.
        delta = None if finished_early else state.posttest_score - state.pretest_score
        competency_map: dict[Competency, CompetencyProgress] = {}
        for competency in Competency:
            round_record = state.competency.get(
                competency.value, {"hits": 0, "misses": 0}
            )
            pre = state.pretest_competency.get(
                competency.value, {"score": 0, "total": 0}
            )
            post = state.posttest_competency.get(
                competency.value, {"score": 0, "total": 0}
            )
            hits = round_record.get("hits", 0)
            misses = round_record.get("misses", 0)
            total_signals = hits + misses
            competency_map[competency] = CompetencyProgress(
                label=COMPETENCY_LABELS[competency],
                hits=hits,
                misses=misses,
                mastery_percent=round(100 * hits / total_signals) if total_signals else 0,
                pre_score=pre.get("score", 0),
                pre_total=pre.get("total", 0),
                post_score=None if finished_early else post.get("score", 0),
                post_total=None if finished_early else post.get("total", 0),
                test_delta=(
                    None if finished_early else post.get("score", 0) - pre.get("score", 0)
                ),
            )
        test_total = engine.bank.assessment_size
        weakest = min(Competency, key=lambda item: competency_accuracy(state, item))
        retried_by_id = {grade.scenario_id: grade for grade in state.retried_grades}
        round_recap = [
            RoundSummary(
                round=index + 1,
                family=grade.family or "",
                verdict=grade.verdict,
                action_correct=grade.action_correct,
                reasoning_score=grade.reasoning_score,
                retried=grade.scenario_id in retried_by_id,
                retry_verdict=(
                    retried_by_id[grade.scenario_id].verdict
                    if grade.scenario_id in retried_by_id
                    else None
                ),
                retry_reasoning_score=(
                    retried_by_id[grade.scenario_id].reasoning_score
                    if grade.scenario_id in retried_by_id
                    else None
                ),
                retry_baseline_score=(
                    _deterministic_coverage(grade)
                    if grade.scenario_id in retried_by_id
                    else None
                ),
            )
            for index, grade in enumerate(state.grades)
        ]
        rounds_needed_nudge = sum(
            1 for grade in state.grades if grade.scenario_id in retried_by_id
        )
        if finished_early:
            share_text = (
                f"I ran Blast Radius: pre {state.pretest_score}/{test_total}, "
                f"{len(state.grades)} agent decisions reviewed, {average}% average tell "
                f"coverage (finished early — post-test not taken)."
            )
        else:
            share_text = (
                f"I completed Blast Radius: pre {state.pretest_score}/{test_total} → "
                f"post {state.posttest_score}/{test_total}, {len(state.grades)} agent decisions, "
                f"{state.rounds_generated} generated variations, and {average}% average tell coverage."
            )
        return LearnerProgress(
            session_id=state.id,
            pretest_score=state.pretest_score,
            posttest_score=state.posttest_score,
            test_total=test_total,
            delta=delta,
            finished_early=finished_early,
            rounds_played=len(state.grades),
            rounds_generated=state.rounds_generated,
            competency_map=competency_map,
            average_reasoning_score=average,
            share_text=share_text,
            rounds=round_recap,
            weakest_competency=CompetencyRef(
                key=weakest.value, label=COMPETENCY_LABELS[weakest]
            ),
            rounds_needed_nudge=rounds_needed_nudge,
        )

    return router
