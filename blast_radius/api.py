import logging
import time
from collections import deque
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from blast_radius.config import Settings
from blast_radius.engine import TrustEngine
from blast_radius.models import (
    COMPETENCY_LABELS,
    Competency,
    CompetencyProgress,
    LearnerProgress,
    PlayerDecision,
    Scenario,
    SessionState,
    competency_for_family,
)
from blast_radius.storage import SessionStore


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(default="demo", pattern=r"^(demo|live)$")


class TestAnswersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[int] = Field(min_length=1, max_length=100)


logger = logging.getLogger(__name__)


class SlidingWindowLimiter:
    def __init__(self, limit: int = 45, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self.hits.get(key)
        if bucket is None:
            bucket = deque()
            self.hits[key] = bucket
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if not bucket:
            self.hits.pop(key, None)
            bucket = deque()
            self.hits[key] = bucket
        if len(bucket) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many requests; pause and try again.")
        bucket.append(now)


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

    def client_host(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def limit_round_request(request: Request, session_id: str) -> None:
        round_ip_limiter.check(f"round-ip:{client_host(request)}")
        round_session_limiter.check(f"round-session:{session_id}")

    def load_session(session_id: str, request: Request) -> SessionState:
        state = store.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found or expired.")
        limiter.check(f"{client_host(request)}:{session_id}")
        return state

    SessionDep = Annotated[SessionState, Depends(load_session)]

    demo_rank = {
        scenario_id: index for index, scenario_id in enumerate(engine.bank.demo_order())
    }

    def score_test(answers: list[int]) -> tuple[int, dict[str, dict[str, int]]]:
        if len(answers) != len(engine.bank.questions):
            raise HTTPException(
                status_code=422,
                detail=f"Exactly {len(engine.bank.questions)} answers are required.",
            )
        competency_scores = {
            competency.value: {"score": 0, "total": 0} for competency in Competency
        }
        for question, answer in zip(engine.bank.questions, answers, strict=True):
            if answer < 0 or answer >= len(question.options):
                raise HTTPException(status_code=422, detail="An answer index is out of range.")
            record = competency_scores[question.competency.value]
            record["total"] += 1
            record["score"] += int(answer == question.correct_index)
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
                demo_rank[scenario_id],
            )
        )
        state.scenario_order[start:] = remaining

    @router.get("/demo/gate-catch")
    def demo_gate_catch(request: Request) -> dict:
        limiter.check(f"gate-catch:{client_host(request)}")
        planted = engine.bank.get("dep-typo-1").model_copy(deep=True)
        planted.id = "demo-planted-hallucination"
        planted.template_ref = "invented-cve-2099-fake-package"
        result = engine.gate.verify(planted)
        return {"passed": result.passed, "reasons": result.reasons}

    @router.post("/sessions", status_code=status.HTTP_201_CREATED)
    def create_session(payload: CreateSessionRequest, request: Request) -> dict:
        session_create_limiter.check(f"session-create:{client_host(request)}")
        session_id = str(uuid4())
        state = SessionState(
            id=session_id,
            mode=payload.mode,
            scenario_order=engine.bank.demo_order(),
        )
        store.save(state)
        return {
            "session_id": state.id,
            "mode": state.mode,
            "rounds_total": len(state.scenario_order),
            "pretest": [question.public_view() for question in engine.bank.questions],
            "live_generation_available": engine.openai.generation_enabled,
            "reasoning_grading": engine.openai.reasoning_grading_state,
        }

    @router.post("/sessions/{session_id}/pretest")
    def submit_pretest(
        payload: TestAnswersRequest,
        state: SessionDep,
    ) -> dict:
        if state.pretest_answers is not None:
            raise HTTPException(status_code=409, detail="Pre-test was already submitted.")
        state.pretest_answers = payload.answers
        state.pretest_score, state.pretest_competency = score_test(payload.answers)
        reorder_demo_suffix(state, 0)
        store.save(state)
        return {"score": state.pretest_score, "total": len(engine.bank.questions)}

    @router.post("/sessions/{session_id}/rounds/next")
    async def next_round(session_id: str, request: Request, state: SessionDep) -> dict:
        if state.pretest_score is None:
            raise HTTPException(status_code=409, detail="Complete the pre-test first.")
        if state.posttest_score is not None:
            raise HTTPException(status_code=409, detail="This session is complete.")
        if state.current_index >= len(state.scenario_order):
            return {
                "complete": True,
                "posttest": [question.public_view() for question in engine.bank.questions],
            }
        limit_round_request(request, session_id)
        if state.active_scenario_json:
            scenario = Scenario.model_validate_json(state.active_scenario_json)
        elif state.mode == "demo":
            scenario = engine.bank.get(state.scenario_order[state.current_index])
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
        else:
            target = engine.bank.get(state.scenario_order[state.current_index])
            weakest = min(Competency, key=lambda item: competency_accuracy(state, item)).value
            difficulty = min(5, 1 + state.current_index)
            scenario, fallback_reason = await engine.next_scenario(
                family=target.family,
                difficulty=difficulty,
                blind_spot=weakest,
                competency=state.competency,
                exclude=set(state.answered_scenario_ids),
                seed=f"{state.id}:{state.current_index}",
            )
            state.last_gate_fallback_reason = fallback_reason
        state.active_scenario_id = scenario.id
        state.active_scenario_json = scenario.model_dump_json()
        store.save(state)
        return {
            "complete": False,
            "round_number": state.current_index + 1,
            "rounds_total": len(state.scenario_order),
            "seconds": max(35, 70 - state.current_index * 5),
            "scenario": scenario.public_view(),
        }

    @router.post("/sessions/{session_id}/decisions")
    async def submit_decision(
        session_id: str,
        request: Request,
        decision: PlayerDecision,
        state: SessionDep,
    ) -> dict:
        limit_round_request(request, session_id)
        if not state.active_scenario_json or not state.active_scenario_id:
            raise HTTPException(status_code=409, detail="Request a round before answering.")
        if decision.scenario_id != state.active_scenario_id:
            raise HTTPException(status_code=409, detail="Decision does not match the active round.")
        if decision.scenario_id in state.answered_scenario_ids:
            raise HTTPException(status_code=409, detail="This round was already answered.")
        scenario = Scenario.model_validate_json(state.active_scenario_json)
        grade = await engine.grade(scenario, decision)
        competency = competency_for_family(scenario.family).value
        record = state.competency.setdefault(competency, {"hits": 0, "misses": 0})
        for tell in scenario.ground_truth.tells:
            record["hits" if tell in grade.matched_tells else "misses"] += 1
        state.grades.append(grade)
        state.answered_scenario_ids.append(scenario.id)
        state.current_index += 1
        state.active_scenario_id = None
        state.active_scenario_json = None
        reorder_demo_suffix(state, state.current_index)
        store.save(state)
        return {
            "grade": grade.model_dump(mode="json"),
            "rounds_remaining": len(state.scenario_order) - state.current_index,
        }

    @router.post("/sessions/{session_id}/posttest")
    def submit_posttest(payload: TestAnswersRequest, state: SessionDep) -> dict:
        if state.current_index < len(state.scenario_order) or state.active_scenario_id:
            raise HTTPException(status_code=409, detail="Finish all rounds before the post-test.")
        if state.posttest_answers is not None:
            raise HTTPException(status_code=409, detail="Post-test was already submitted.")
        state.posttest_answers = payload.answers
        state.posttest_score, state.posttest_competency = score_test(payload.answers)
        store.save(state)
        return {"score": state.posttest_score, "total": len(engine.bank.questions)}

    @router.get("/sessions/{session_id}/results", response_model=LearnerProgress)
    def results(state: SessionDep) -> LearnerProgress:
        if state.pretest_score is None or state.posttest_score is None:
            raise HTTPException(status_code=409, detail="Complete the session to view results.")
        average = (
            round(sum(grade.reasoning_score for grade in state.grades) / len(state.grades))
            if state.grades
            else 0
        )
        delta = state.posttest_score - state.pretest_score
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
                post_score=post.get("score", 0),
                post_total=post.get("total", 0),
                test_delta=post.get("score", 0) - pre.get("score", 0),
            )
        test_total = len(engine.bank.questions)
        return LearnerProgress(
            session_id=state.id,
            pretest_score=state.pretest_score,
            posttest_score=state.posttest_score,
            test_total=test_total,
            delta=delta,
            rounds_played=len(state.grades),
            competency_map=competency_map,
            average_reasoning_score=average,
            share_text=(
                f"I completed Blast Radius: pre {state.pretest_score}/{test_total} → "
                f"post {state.posttest_score}/{test_total}, {len(state.grades)} agent decisions, "
                f"and {average}% average reasoning."
            ),
        )

    return router
