import time
from collections import defaultdict, deque
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from blast_radius.config import Settings
from blast_radius.engine import TrustEngine
from blast_radius.models import (
    LearnerProgress,
    PlayerDecision,
    Scenario,
    SessionState,
)
from blast_radius.storage import SessionStore


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(default="demo", pattern=r"^(demo|live)$")


class TestAnswersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[int] = Field(min_length=5, max_length=5)


class SlidingWindowLimiter:
    def __init__(self, limit: int = 45, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many requests; pause and try again.")
        bucket.append(now)


def build_router(settings: Settings, engine: TrustEngine, store: SessionStore) -> APIRouter:
    router = APIRouter(prefix="/api")
    limiter = SlidingWindowLimiter()

    def load_session(session_id: str, request: Request) -> SessionState:
        limiter.check(f"{request.client.host if request.client else 'unknown'}:{session_id}")
        state = store.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found or expired.")
        return state

    SessionDep = Annotated[SessionState, Depends(load_session)]

    def score_test(answers: list[int]) -> int:
        if len(answers) != len(engine.bank.questions):
            raise HTTPException(status_code=422, detail="Exactly five answers are required.")
        for question, answer in zip(engine.bank.questions, answers, strict=True):
            if answer < 0 or answer >= len(question.options):
                raise HTTPException(status_code=422, detail="An answer index is out of range.")
        return sum(
            answer == question.correct_index
            for answer, question in zip(answers, engine.bank.questions, strict=True)
        )

    @router.post("/sessions", status_code=status.HTTP_201_CREATED)
    def create_session(payload: CreateSessionRequest, request: Request) -> dict:
        limiter.check(request.client.host if request.client else "unknown")
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
            "live_generation_available": engine.openai.enabled,
        }

    @router.post("/sessions/{session_id}/pretest")
    def submit_pretest(
        payload: TestAnswersRequest,
        state: SessionDep,
    ) -> dict:
        if state.pretest_answers is not None:
            raise HTTPException(status_code=409, detail="Pre-test was already submitted.")
        state.pretest_answers = payload.answers
        state.pretest_score = score_test(payload.answers)
        store.save(state)
        return {"score": state.pretest_score, "total": len(engine.bank.questions)}

    @router.post("/sessions/{session_id}/rounds/next")
    async def next_round(state: SessionDep) -> dict:
        if state.pretest_score is None:
            raise HTTPException(status_code=409, detail="Complete the pre-test first.")
        if state.posttest_score is not None:
            raise HTTPException(status_code=409, detail="This session is complete.")
        if state.current_index >= len(state.scenario_order):
            return {
                "complete": True,
                "posttest": [question.public_view() for question in engine.bank.questions],
            }
        if state.active_scenario_json:
            scenario = Scenario.model_validate_json(state.active_scenario_json)
        elif state.mode == "demo":
            scenario = engine.bank.get(state.scenario_order[state.current_index])
            gate = engine.gate.verify(scenario)
            if not gate.passed:
                raise HTTPException(status_code=503, detail="Curated scenario failed verification.")
        else:
            target = engine.bank.get(state.scenario_order[state.current_index])
            weakest = min(
                state.competency,
                key=lambda key: state.competency[key].get("hits", 0),
                default=target.family.value,
            )
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
    async def submit_decision(decision: PlayerDecision, state: SessionDep) -> dict:
        if not state.active_scenario_json or not state.active_scenario_id:
            raise HTTPException(status_code=409, detail="Request a round before answering.")
        if decision.scenario_id != state.active_scenario_id:
            raise HTTPException(status_code=409, detail="Decision does not match the active round.")
        if decision.scenario_id in state.answered_scenario_ids:
            raise HTTPException(status_code=409, detail="This round was already answered.")
        scenario = Scenario.model_validate_json(state.active_scenario_json)
        grade = await engine.grade(scenario, decision)
        for tell in scenario.ground_truth.tells:
            record = state.competency.setdefault(tell, {"hits": 0, "misses": 0})
            record["hits" if tell in grade.matched_tells else "misses"] += 1
        state.grades.append(grade)
        state.answered_scenario_ids.append(scenario.id)
        state.current_index += 1
        state.active_scenario_id = None
        state.active_scenario_json = None
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
        state.posttest_score = score_test(payload.answers)
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
        return LearnerProgress(
            session_id=state.id,
            pretest_score=state.pretest_score,
            posttest_score=state.posttest_score,
            delta=delta,
            rounds_played=len(state.grades),
            competency_map=state.competency,
            average_reasoning_score=average,
            share_text=(
                f"I completed Blast Radius: {len(state.grades)} agent decisions, "
                f"{average}% reasoning score, and a {delta:+d} competency delta."
            ),
        )

    return router
