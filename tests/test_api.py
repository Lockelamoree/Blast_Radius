import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

from fastapi import HTTPException
from fastapi.testclient import TestClient

from blast_radius.api import (
    SessionMutationLocks,
    SlidingWindowLimiter,
    assessment_option_order,
)
from blast_radius.engine import TrustEngine
from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.openai_adapter import (
    ModelGateReview,
    ModelReasoningReview,
    OpenAIAdapter,
    StructuredCallResult,
)
from blast_radius.main import create_app
from blast_radius.models import (
    COMPETENCY_LABELS,
    AssessmentForm,
    Competency,
    GateResult,
    ScenarioFamily,
)

PRETEST_CORRECT_OPTIONS = {
    "q-command": "Path scope and reversibility",
    "q-package": "Verify registry provenance and package history",
    "q-manifest": "Its capabilities exceed its stated job",
    "q-diff": "The behavior is absent from the change description",
    "q-context": "As untrusted content and rejected",
}


def create_started_session(client):
    created = client.post("/api/sessions", json={"mode": "demo"})
    assert created.status_code == 201
    body = created.json()
    session_id = body["session_id"]
    answers = [
        next(
            index
            for index, option in enumerate(question["options"])
            if option != PRETEST_CORRECT_OPTIONS[question["id"]]
        )
        for question in body["pretest"]
    ]
    pretest = client.post(
        f"/api/sessions/{session_id}/pretest",
        json={"answers": answers},
    )
    assert pretest.status_code == 200
    return session_id


def assessment_answers(bank, public_questions, *, incorrect_ids=frozenset()):
    lookup = {question.id: question for question in bank.questions}
    answers = []
    for public in public_questions:
        question = lookup[public["id"]]
        correct_text = question.options[question.correct_index]
        if question.id in incorrect_ids:
            answers.append(
                next(
                    index
                    for index, option in enumerate(public["options"])
                    if option != correct_text
                )
            )
        else:
            answers.append(public["options"].index(correct_text))
    return answers


def test_assessment_option_order_is_session_stable() -> None:
    first = assessment_option_order("session-a", AssessmentForm.PRE, "q-command", 4)
    assert first == assessment_option_order(
        "session-a", AssessmentForm.PRE, "q-command", 4
    )
    assert first != assessment_option_order(
        "session-b", AssessmentForm.PRE, "q-command", 4
    )
    assert sorted(first) == [0, 1, 2, 3]


def test_sliding_window_limiter_is_atomic_across_threads() -> None:
    limit = 8
    attempts = 24
    limiter = SlidingWindowLimiter(limit=limit, window_seconds=60)
    barrier = Barrier(attempts)

    def check_once() -> bool:
        barrier.wait()
        try:
            limiter.check("shared")
        except HTTPException as exc:
            assert exc.status_code == 429
            return False
        return True

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        accepted = list(pool.map(lambda _: check_once(), range(attempts)))

    assert sum(accepted) == limit
    assert len(limiter.hits["shared"]) == limit


def test_health_and_home(client) -> None:
    assert client.get("/").status_code == 200
    # Uptime monitors default to HEAD; it must not 405.
    assert client.head("/").status_code == 200
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["bank_scenarios"] >= 18
    assert health.json()["reasoning_grading"] == "off"
    assert health.json()["live_generation"] is False
    assert health.json()["live_generation_reason"] == "off"
    assert health.json()["critic_model"] == "gpt-5.6-sol"
    assert "api_key" not in str(health.json()).lower()


def test_api_documentation_is_off_by_default_and_explicitly_enabled(
    client, test_settings
) -> None:
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404

    with TestClient(create_app(replace(test_settings, enable_docs=True))) as docs_client:
        assert docs_client.get("/api/docs").status_code == 200
        assert docs_client.get("/api/openapi.json").status_code == 200


def test_round_response_hides_ground_truth(client) -> None:
    session_id = create_started_session(client)
    response = client.post(f"/api/sessions/{session_id}/rounds/next")
    assert response.status_code == 200
    body = response.json()
    assert "ground_truth" not in str(body)
    assert "correct_action" not in str(body)
    assert body["provenance"] == "verified"
    assert body["generation_status"] == "not_requested"


def test_gate_catch_rejects_planted_hallucination_without_leaking_it(client) -> None:
    tell = client.get("/api/demo/gate-catch?case=tell")
    assert tell.status_code == 200
    assert tell.json()["case"] == "tell"
    assert tell.json()["planted_claim"] == "hidden remote code execution backdoor"
    assert tell.json()["reasons"] == [
        "presented artifacts do not support declared tell: hidden remote code execution backdoor"
    ]
    citation = client.get("/api/demo/gate-catch?case=citation")
    assert citation.status_code == 200
    assert citation.json()["case"] == "citation"
    assert citation.json()["planted_claim"] == "off-catalog security receipt"
    assert citation.json()["reasons"] == [
        "evidence source is not approved for this template"
    ]
    assert "ground_truth" not in tell.text + citation.text


def test_gate_catch_is_rate_limited(client) -> None:
    for _ in range(45):
        assert client.get("/api/demo/gate-catch").status_code == 200
    assert client.get("/api/demo/gate-catch").status_code == 429


def test_learn_field_guide_covers_every_family_with_cited_sources(client) -> None:
    response = client.get("/api/learn")
    assert response.status_code == 200
    modules = response.json()["modules"]
    families = [module["family"] for module in modules]
    assert set(families) == {family.value for family in ScenarioFamily}
    assert len(families) == len(set(families)) == len(ScenarioFamily)
    for module in modules:
        assert module["title"] and module["threat"] and module["safe_default"]
        assert module["tells"], "each family must list tells to spot"
        assert module["sources"], "each family must cite at least one source"
        for source in module["sources"]:
            assert source["url"].startswith("https://")
            assert source["title"] and source["publisher"]


def test_toolkit_covers_every_family_with_actionable_defenses(client) -> None:
    response = client.get("/api/toolkit")
    assert response.status_code == 200
    cards = response.json()["cards"]
    assert {card["family"] for card in cards} == {f.value for f in ScenarioFamily}
    for card in cards:
        assert card["title"] and card["summary"]
        assert card["steps"], "each card needs concrete steps"
        assert card["snippets"], "each card needs at least one copy-paste snippet"
        for snippet in card["snippets"]:
            assert snippet["label"] and snippet["code"]
        for tool in card.get("tools", []):
            assert tool["url"].startswith("https://")
            assert tool["name"]


def test_learn_endpoint_is_rate_limited(client) -> None:
    for _ in range(45):
        assert client.get("/api/learn").status_code == 200
    assert client.get("/api/learn").status_code == 429


def test_unknown_session_ids_do_not_allocate_rate_limit_buckets(
    test_settings, monkeypatch
) -> None:
    checked: list[str] = []
    original_check = SlidingWindowLimiter.check

    def record_check(limiter, key: str) -> None:
        checked.append(key)
        original_check(limiter, key)

    monkeypatch.setattr(SlidingWindowLimiter, "check", record_check)
    with TestClient(create_app(test_settings)) as unknown_client:
        for index in range(20):
            response = unknown_client.get(f"/api/sessions/missing-{index}/results")
            assert response.status_code == 404

    assert checked == []


def test_duplicate_decision_is_rejected(client) -> None:
    session_id = create_started_session(client)
    round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    scenario_id = round_data["scenario"]["id"]
    decision = {
        "scenario_id": scenario_id,
        "action": "sandbox",
        "reasoning_text": "The destructive command should stay inside the generated workspace directory.",
        "blast_radius_config": {
            "readable_paths": ["/workspace/htmlcov"],
            "writable_paths": ["/workspace/htmlcov"],
            "network_enabled": False,
            "network_allowlist": [],
            "capabilities": ["delete-generated-files"],
        },
    }
    assert client.post(f"/api/sessions/{session_id}/decisions", json=decision).status_code == 200
    duplicate = client.post(f"/api/sessions/{session_id}/decisions", json=decision)
    assert duplicate.status_code == 409
    # The retrying client must hear the truth so it can advance instead of erroring.
    assert duplicate.json()["detail"] == "This round was already answered."


def test_idempotent_round_replays_do_not_consume_the_session_cap(client) -> None:
    session_id = create_started_session(client)
    first = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    # 40 replays exceed the 30-per-session cap; replays of the active round are free.
    for _ in range(40):
        replay = client.post(f"/api/sessions/{session_id}/rounds/next")
        assert replay.status_code == 200
        assert replay.json()["scenario"]["id"] == first["scenario"]["id"]
    decision = {
        "scenario_id": first["scenario"]["id"],
        "action": "reject",
        "reasoning_text": "Replays must never lock a session out of its own game.",
    }
    assert (
        client.post(f"/api/sessions/{session_id}/decisions", json=decision).status_code
        == 200
    )


def test_session_mutation_locks_release_idle_keys() -> None:
    locks = SessionMutationLocks()

    async def wait_for_lock() -> None:
        async with locks.hold("session-1"):
            raise AssertionError("cancelled waiter unexpectedly acquired the lock")

    async def exercise_lock() -> None:
        async with locks.hold("session-1"):
            assert locks.active_key_count == 1
            waiter = asyncio.create_task(wait_for_lock())
            await asyncio.sleep(0)
            waiter.cancel()
            try:
                await waiter
            except asyncio.CancelledError:
                pass

    asyncio.run(exercise_lock())
    assert locks.active_key_count == 0


def test_concurrent_duplicate_decisions_grade_exactly_once(
    client, monkeypatch
) -> None:
    session_id = create_started_session(client)
    round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    scenario_id = round_data["scenario"]["id"]
    decision = {
        "scenario_id": scenario_id,
        "action": "sandbox",
        "reasoning_text": (
            "The destructive cleanup needs a narrow generated-directory boundary."
        ),
        "blast_radius_config": {
            "readable_paths": ["/workspace/htmlcov"],
            "writable_paths": ["/workspace/htmlcov"],
            "network_enabled": False,
            "network_allowlist": [],
            "capabilities": ["delete-generated-files"],
        },
    }
    real_grade = TrustEngine.grade
    identifiers: list[str | None] = []

    async def slow_grade(
        engine,
        scenario,
        player_decision,
        *,
        safety_identifier=None,
        allow_critic=True,
        session_budget=None,
    ):
        identifiers.append(safety_identifier)
        await asyncio.sleep(0.05)
        return await real_grade(
            engine,
            scenario,
            player_decision,
            safety_identifier=safety_identifier,
            allow_critic=allow_critic,
            session_budget=session_budget,
        )

    monkeypatch.setattr(TrustEngine, "grade", slow_grade)

    def submit():
        return client.post(f"/api/sessions/{session_id}/decisions", json=decision)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert identifiers == [session_id]


def test_full_demo_session(client, test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    created = client.post("/api/sessions", json={"mode": "demo"}).json()
    session_id = created["session_id"]
    pre_answers = assessment_answers(
        bank,
        created["pretest"],
        incorrect_ids={question["id"] for question in created["pretest"]},
    )
    pretest = client.post(
        f"/api/sessions/{session_id}/pretest",
        json={"answers": pre_answers},
    )
    assert pretest.json() == {"score": 0, "total": 5}
    for _ in range(6):
        round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
        scenario_id = round_data["scenario"]["id"]
        family = round_data["scenario"]["family"]
        if scenario_id == "cmd-cleanup-2":
            payload = {
                "scenario_id": scenario_id,
                "action": "sandbox",
                "reasoning_text": "Bound the destructive generated-directory cleanup to the workspace.",
                "blast_radius_config": {
                    "readable_paths": ["/workspace/htmlcov"],
                    "writable_paths": ["/workspace/htmlcov"],
                    "network_enabled": False,
                    "network_allowlist": [],
                    "capabilities": ["delete-generated-files"],
                },
            }
        else:
            payload = {
                "scenario_id": scenario_id,
                "action": "reject",
                "reasoning_text": "The artifacts show an unapproved secret, scope, provenance, or egress risk.",
            }
        response = client.post(f"/api/sessions/{session_id}/decisions", json=payload)
        assert response.status_code == 200, (family, response.text)
    done = client.post(f"/api/sessions/{session_id}/rounds/next")
    assert done.json()["complete"] is True
    repeated_done = client.post(f"/api/sessions/{session_id}/rounds/next")
    assert repeated_done.json()["posttest"] == done.json()["posttest"]
    assert "correct_index" not in done.text
    assert '"form"' not in done.text
    post_answers = assessment_answers(bank, done.json()["posttest"])
    post = client.post(
        f"/api/sessions/{session_id}/posttest",
        json={"answers": post_answers},
    )
    assert post.status_code == 200
    result = client.get(f"/api/sessions/{session_id}/results")
    assert result.status_code == 200
    assert result.json()["delta"] == 5
    assert result.json()["rounds_played"] == 6
    assert result.json()["test_total"] == 5
    assert set(result.json()["competency_map"]) == {item.value for item in Competency}
    for competency in result.json()["competency_map"].values():
        assert competency["pre_score"] == 0
        assert competency["pre_total"] == 1
        assert competency["post_score"] == 1
        assert competency["post_total"] == 1
        assert competency["test_delta"] == 1
        assert competency["label"]
    assert "hidden credential upload" not in result.text
    assert "pre 0/5 → post 5/5" in result.json()["share_text"]
    recap = result.json()["rounds"]
    assert [entry["round"] for entry in recap] == list(range(1, 7))
    assert {entry["family"] for entry in recap} == {item.value for item in ScenarioFamily}
    for entry in recap:
        assert set(entry) == {
            "round",
            "family",
            "verdict",
            "action_correct",
            "reasoning_score",
            "retried",
            "retry_verdict",
            "retry_reasoning_score",
            "retry_baseline_score",
        }
        assert entry["retried"] is False
    weakest = result.json()["weakest_competency"]
    assert weakest["key"] in {item.value for item in Competency}
    assert weakest["label"]


def test_finish_early_returns_honest_partial_results(client) -> None:
    session_id = create_started_session(client)
    for _ in range(2):
        round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
        assert client.post(
            f"/api/sessions/{session_id}/decisions",
            json={
                "scenario_id": round_data["scenario"]["id"],
                "action": "reject",
                "reasoning_text": "The displayed scope or provenance is not trusted enough.",
            },
        ).status_code == 200

    finished = client.post(f"/api/sessions/{session_id}/finish-early")
    assert finished.status_code == 200
    assert finished.json() == {"finished_early": True, "rounds_played": 2}

    body = client.get(f"/api/sessions/{session_id}/results").json()
    assert body["finished_early"] is True
    assert body["posttest_score"] is None
    assert body["delta"] is None
    assert body["rounds_played"] == 2
    assert len(body["rounds"]) == 2
    for competency in body["competency_map"].values():
        assert competency["post_score"] is None
        assert competency["post_total"] is None
        assert competency["test_delta"] is None
    assert "finished early" in body["share_text"]

    # A finished-early session is complete: no more rounds and no post-test.
    assert client.post(f"/api/sessions/{session_id}/rounds/next").status_code == 409
    assert client.post(
        f"/api/sessions/{session_id}/posttest",
        json={"answers": [0, 0, 0, 0, 0]},
    ).status_code == 409


def test_demo_rounds_name_the_adaptive_focus_after_the_first(client) -> None:
    session_id = create_started_session(client)
    first = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    assert first["round_number"] == 1
    # Round 1 has no prior signal, so no adaptive focus is claimed.
    assert first["adaptive_focus"] is None
    client.post(
        f"/api/sessions/{session_id}/decisions",
        json={
            "scenario_id": first["scenario"]["id"],
            "action": "reject",
            "reasoning_text": "The displayed scope or provenance is not trusted enough.",
        },
    )
    second = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    assert second["round_number"] == 2
    assert second["adaptive_focus"] in set(COMPETENCY_LABELS.values())


def test_finish_early_requires_a_played_round(client) -> None:
    session_id = create_started_session(client)
    # Nothing has been shown yet, so there is no honest partial state to report.
    refused = client.post(f"/api/sessions/{session_id}/finish-early")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Play at least one round before finishing early."


def test_reflect_returns_a_bounded_coach_reply_for_a_bank_round(client) -> None:
    session_id = create_started_session(client)
    round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    scenario_id = round_data["scenario"]["id"]
    client.post(
        f"/api/sessions/{session_id}/decisions",
        json={
            "scenario_id": scenario_id,
            "action": "reject",
            "reasoning_text": "This does not feel right but I cannot say exactly why.",
        },
    )
    reflect = client.post(
        f"/api/sessions/{session_id}/rounds/reflect",
        json={"scenario_id": scenario_id, "question": "What did I miss on this round?"},
    )
    assert reflect.status_code == 200
    body = reflect.json()
    assert body["feedback"]
    # No key in tests, so the deterministic coach answers.
    assert body["coached_by"] == "deterministic"
    # One exchange per round — a second reflection on the same round is refused.
    again = client.post(
        f"/api/sessions/{session_id}/rounds/reflect",
        json={"scenario_id": scenario_id, "question": "Can you tell me more please?"},
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "You have already used this round's reflection."


def test_reflect_requires_an_answered_bank_round(client) -> None:
    session_id = create_started_session(client)
    round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    # A round that was never answered cannot be reflected on.
    unanswered = client.post(
        f"/api/sessions/{session_id}/rounds/reflect",
        json={"scenario_id": round_data["scenario"]["id"], "question": "Why is this wrong?"},
    )
    assert unanswered.status_code == 409
    # Generated rounds keep no server-side ground truth, so live-* ids are refused.
    live = client.post(
        f"/api/sessions/{session_id}/rounds/reflect",
        json={"scenario_id": "live-deadbeef", "question": "What about this one then?"},
    )
    assert live.status_code == 409
    assert live.json()["detail"] == "Reflection is available for verified rounds only."


def test_demo_reorders_only_the_verified_deck_by_weakest_competency(
    test_settings, monkeypatch
) -> None:
    async def generation_must_not_run(*args, **kwargs):
        raise AssertionError("demo adaptation must not invoke live generation")

    monkeypatch.setattr(TrustEngine, "next_scenario", generation_must_not_run)

    with TestClient(create_app(test_settings)) as adaptive_client:
        bank = ScenarioBank(test_settings.data_dir)
        created = adaptive_client.post("/api/sessions", json={"mode": "demo"}).json()
        session_id = created["session_id"]
        answers = assessment_answers(
            bank,
            created["pretest"],
            incorrect_ids={"q-manifest"},
        )
        pretest = adaptive_client.post(
            f"/api/sessions/{session_id}/pretest",
            json={"answers": answers},
        )
        assert pretest.status_code == 200

        played = []
        for _ in range(6):
            round_data = adaptive_client.post(
                f"/api/sessions/{session_id}/rounds/next"
            ).json()
            scenario_id = round_data["scenario"]["id"]
            played.append(scenario_id)
            decision = adaptive_client.post(
                f"/api/sessions/{session_id}/decisions",
                json={
                    "scenario_id": scenario_id,
                    "action": "reject",
                    "reasoning_text": (
                        "The evidence shows an excessive capability or egress mismatch."
                    ),
                },
            )
            assert decision.status_code == 200

    played_families = [bank.get(scenario_id).family.value for scenario_id in played]
    # The weakest competency was capabilities (q-manifest answered wrong); both
    # capability families sort to the front, overscoped_tool before skill_marketplace
    # by canonical family rank — regardless of which seeded members were drawn.
    assert played_families[:2] == [
        ScenarioFamily.OVERSCOPED_TOOL.value,
        ScenarioFamily.SKILL_MARKETPLACE.value,
    ]
    # Every threat family still appears exactly once in the per-session deck.
    assert set(played_families) == {family.value for family in ScenarioFamily}
    assert len(played) == len(set(played)) == 6


def test_live_rounds_persist_generation_provenance_and_respect_caps(
    test_settings, monkeypatch
) -> None:
    calls: dict[str, list[str]] = {"generate": [], "gate": [], "reasoning": []}

    async def probe(self) -> None:
        self.reasoning_grading_state = "live"

    async def generate(
        self,
        base,
        template,
        difficulty,
        blind_spot,
        *,
        safety_identifier=None,
        session_budget=None,
    ):
        assert session_budget is not None and session_budget.reserve()
        calls["generate"].append(base.id)
        return base.presentation.model_copy(
            update={
                "eyebrow": f"Verified-anchor variation {len(calls['generate'])}",
                "agent_note": f"Reskinned safely: {base.presentation.agent_note}",
            }
        )

    async def critic_gate(
        self,
        scenario,
        template,
        *,
        safety_identifier=None,
        session_budget=None,
    ):
        assert session_budget is not None and session_budget.reserve()
        calls["gate"].append(scenario.id)
        return StructuredCallResult(
            value=ModelGateReview(passed=True, reasons=[]),
            response_id=f"resp_gate_{len(calls['gate'])}",
            response_model="gpt-5.6-sol",
        )

    async def critique(
        self,
        scenario,
        decision,
        *,
        safety_identifier=None,
        session_budget=None,
    ):
        assert session_budget is not None and session_budget.reserve()
        calls["reasoning"].append(scenario.id)
        return StructuredCallResult(
            value=ModelReasoningReview(
                matched_tells=[],
                followup="Which artifact supports your decision?",
            ),
            response_id="resp_reasoning_fallback",
            response_model="gpt-5.6-sol",
        )

    monkeypatch.setattr(OpenAIAdapter, "probe_reasoning_grading", probe)
    monkeypatch.setattr(OpenAIAdapter, "generate", generate)
    monkeypatch.setattr(OpenAIAdapter, "critic_gate", critic_gate)
    monkeypatch.setattr(OpenAIAdapter, "critique_reasoning", critique)
    settings = replace(
        test_settings,
        openai_api_key="test-key",
        live_generation=True,
        generated_rounds_per_session=5,
        session_llm_call_cap=12,
    )

    with TestClient(create_app(settings)) as live_client:
        for _ in range(20):
            health = live_client.get("/healthz").json()
            if health["live_generation"]:
                break
            time.sleep(0.01)
        assert health["live_generation_reason"] == "available"

        bank = ScenarioBank(settings.data_dir)
        created = live_client.post("/api/sessions", json={"mode": "live"}).json()
        session_id = created["session_id"]
        pre_answers = assessment_answers(bank, created["pretest"])
        assert live_client.post(
            f"/api/sessions/{session_id}/pretest",
            json={"answers": pre_answers},
        ).status_code == 200

        shown_ids: list[str] = []
        for index in range(6):
            first = live_client.post(f"/api/sessions/{session_id}/rounds/next")
            repeated = live_client.post(f"/api/sessions/{session_id}/rounds/next")
            assert first.status_code == repeated.status_code == 200
            assert first.json() == repeated.json()
            round_data = first.json()
            shown_ids.append(round_data["scenario"]["id"])
            if index < 5:
                assert round_data["provenance"] == "generated"
                assert round_data["generation_status"] == "generated"
            else:
                assert round_data["provenance"] == "verified"
                assert round_data["generation_status"] == "fell_back"
            assert live_client.post(
                f"/api/sessions/{session_id}/decisions",
                json={
                    "scenario_id": round_data["scenario"]["id"],
                    "action": "reject",
                    "reasoning_text": "The displayed scope and provenance are not sufficiently trusted.",
                },
            ).status_code == 200

        terminal = live_client.post(f"/api/sessions/{session_id}/rounds/next").json()
        post_answers = assessment_answers(bank, terminal["posttest"])
        assert live_client.post(
            f"/api/sessions/{session_id}/posttest",
            json={"answers": post_answers},
        ).status_code == 200
        results = live_client.get(f"/api/sessions/{session_id}/results").json()

    assert results["rounds_generated"] == 5
    assert len(calls["generate"]) == len(calls["gate"]) == 5
    assert len(calls["reasoning"]) == 1
    assert len(calls["generate"]) == len(set(calls["generate"]))
    assert len(shown_ids) == len(set(shown_ids))


def test_session_creation_has_a_per_ip_limit(test_settings) -> None:
    settings = replace(test_settings, session_create_limit_per_hour=1)
    with TestClient(create_app(settings)) as limited_client:
        assert limited_client.post("/api/sessions", json={"mode": "demo"}).status_code == 201
        blocked = limited_client.post("/api/sessions", json={"mode": "demo"})
    assert blocked.status_code == 429


def test_round_requests_have_a_per_session_cap(test_settings) -> None:
    # Cap of 2 = one fresh round fetch + its decision; the next fresh round must block.
    settings = replace(test_settings, session_round_request_cap=2)
    with TestClient(create_app(settings)) as limited_client:
        session_id = create_started_session(limited_client)
        first = limited_client.post(f"/api/sessions/{session_id}/rounds/next")
        assert first.status_code == 200
        # Replaying the active round is idempotent and free even at the cap.
        replay = limited_client.post(f"/api/sessions/{session_id}/rounds/next")
        assert replay.status_code == 200
        assert replay.json()["scenario"]["id"] == first.json()["scenario"]["id"]
        decision = {
            "scenario_id": first.json()["scenario"]["id"],
            "action": "reject",
            "reasoning_text": "Only fresh rounds may consume the per-session cap.",
        }
        assert (
            limited_client.post(
                f"/api/sessions/{session_id}/decisions", json=decision
            ).status_code
            == 200
        )
        # The next FRESH round is the third capped request and must be blocked.
        blocked = limited_client.post(f"/api/sessions/{session_id}/rounds/next")
    assert blocked.status_code == 429


def test_terminal_round_payload_bypasses_exhausted_round_bucket(test_settings) -> None:
    settings = replace(test_settings, session_round_request_cap=12)
    with TestClient(create_app(settings)) as limited_client:
        session_id = create_started_session(limited_client)
        for _ in range(6):
            round_data = limited_client.post(
                f"/api/sessions/{session_id}/rounds/next"
            ).json()
            scenario_id = round_data["scenario"]["id"]
            payload = {
                "scenario_id": scenario_id,
                "action": "reject",
                "reasoning_text": "The displayed artifact exceeds the stated trust boundary.",
            }
            if scenario_id == "cmd-cleanup-2":
                payload["action"] = "sandbox"
                payload["blast_radius_config"] = {
                    "readable_paths": ["/workspace/htmlcov"],
                    "writable_paths": ["/workspace/htmlcov"],
                    "network_enabled": False,
                    "network_allowlist": [],
                    "capabilities": ["delete-generated-files"],
                }
            assert limited_client.post(
                f"/api/sessions/{session_id}/decisions", json=payload
            ).status_code == 200

        terminal = limited_client.post(f"/api/sessions/{session_id}/rounds/next")

    assert terminal.status_code == 200
    assert terminal.json()["complete"] is True


def test_gate_failing_demo_scenario_is_replaced(test_settings, monkeypatch) -> None:
    from blast_radius.engine.gate import CorrectnessGate

    real_verify = CorrectnessGate.verify

    def reject_one(self, scenario):
        if scenario.id == "cmd-cleanup-2":
            return GateResult(
                passed=False,
                reasons=["planted runtime contradiction"],
                scenario_id=scenario.id,
            )
        return real_verify(self, scenario)

    monkeypatch.setattr(CorrectnessGate, "verify", reject_one)
    with TestClient(create_app(test_settings)) as recovery_client:
        session_id = create_started_session(recovery_client)
        first = recovery_client.post(f"/api/sessions/{session_id}/rounds/next")
        repeated = recovery_client.post(f"/api/sessions/{session_id}/rounds/next")

    assert first.status_code == 200
    assert first.json()["scenario"]["id"] != "cmd-cleanup-2"
    assert first.json()["scenario"]["family"] == "dangerous_command"
    assert repeated.json()["scenario"]["id"] == first.json()["scenario"]["id"]


def test_test_answer_count_reaches_dynamic_bank_validation(client) -> None:
    created = client.post("/api/sessions", json={"mode": "demo"}).json()
    response = client.post(
        f"/api/sessions/{created['session_id']}/pretest",
        json={"answers": [1, 1, 1, 1, 1, 1]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Exactly 5 answers are required."


def test_session_assessments_preserve_options_but_shuffle_positions(
    client, test_settings
) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    created = client.post("/api/sessions", json={"mode": "demo"}).json()

    for public in created["pretest"]:
        source = next(question for question in bank.questions if question.id == public["id"])
        assert set(public["options"]) == set(source.options)
        assert public["options"] != source.options
        assert "correct_index" not in public
        assert "form" not in public


def _answered_wrong_or_partial(client: TestClient) -> tuple[str, str, str]:
    """Complete a full demo pretest, then answer round 1 'reject' with tell-free
    reasoning — partial (reject scenario) or wrong (approve/sandbox), both
    retriable in a non-drill session. Returns (session_id, scenario_id, verdict)."""
    session_id = create_started_session(client)
    round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    scenario_id = round_data["scenario"]["id"]
    graded = client.post(
        f"/api/sessions/{session_id}/decisions",
        json={
            "scenario_id": scenario_id,
            "action": "reject",
            "reasoning_text": "I have a general bad feeling about this request overall.",
        },
    ).json()
    return session_id, scenario_id, graded["grade"]["verdict"]


def test_retry_regrades_deterministically_without_touching_budget(client) -> None:
    session_id, scenario_id, verdict = _answered_wrong_or_partial(client)
    assert verdict in {"partial", "wrong"}
    response = client.post(
        f"/api/sessions/{session_id}/rounds/retry",
        json={
            "scenario_id": scenario_id,
            "reasoning_text": "On reflection this reads as an unapproved secret and network egress risk.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["initial"]["verdict"] == verdict
    assert body["coached"]["graded_by"] == "deterministic"
    assert body["coached"]["critic_used"] is False
    assert "improved" in body
    # Second retry on the same round is refused.
    again = client.post(
        f"/api/sessions/{session_id}/rounds/retry",
        json={"scenario_id": scenario_id, "reasoning_text": "Another attempt at the reasoning."},
    )
    assert again.status_code == 409


def test_retry_rejects_unanswered_generated_and_unknown_rounds(client) -> None:
    # A non-drill session so the drill guard doesn't mask the checks under test.
    session_id = create_started_session(client)
    round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    scenario_id = round_data["scenario"]["id"]
    # Not answered yet.
    unanswered = client.post(
        f"/api/sessions/{session_id}/rounds/retry",
        json={"scenario_id": scenario_id, "reasoning_text": "Trying to revise too early here."},
    )
    assert unanswered.status_code == 409
    # A generated (live-*) id is never retriable.
    generated = client.post(
        f"/api/sessions/{session_id}/rounds/retry",
        json={"scenario_id": "live-deadbeef", "reasoning_text": "Revising a generated round."},
    )
    assert generated.status_code == 409


def test_retry_refuses_correct_rounds_and_feeds_results(client, test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    created = client.post("/api/sessions", json={"mode": "demo"}).json()
    session_id = created["session_id"]
    pre_answers = assessment_answers(bank, created["pretest"])
    client.post(f"/api/sessions/{session_id}/pretest", json={"answers": pre_answers})

    retried_partial: str | None = None
    for _ in range(6):
        round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
        scenario_id = round_data["scenario"]["id"]
        if scenario_id == "cmd-cleanup-2":
            payload = {
                "scenario_id": scenario_id,
                "action": "sandbox",
                "reasoning_text": "Bound the destructive generated-directory cleanup to the workspace.",
                "blast_radius_config": {
                    "readable_paths": ["/workspace/htmlcov"],
                    "writable_paths": ["/workspace/htmlcov"],
                    "network_enabled": False,
                    "network_allowlist": [],
                    "capabilities": ["delete-generated-files"],
                },
            }
        else:
            payload = {
                "scenario_id": scenario_id,
                "action": "reject",
                "reasoning_text": "I have a general bad feeling about this request overall.",
            }
        grade = client.post(f"/api/sessions/{session_id}/decisions", json=payload).json()["grade"]
        if grade["verdict"] == "correct" and retried_partial is None:
            # A correct round cannot be revised.
            refused = client.post(
                f"/api/sessions/{session_id}/rounds/retry",
                json={"scenario_id": scenario_id, "reasoning_text": "Trying to revise a correct round."},
            )
            assert refused.status_code == 409
        if grade["verdict"] in {"partial", "wrong"} and retried_partial is None:
            retried_partial = scenario_id
            client.post(
                f"/api/sessions/{session_id}/rounds/retry",
                json={
                    "scenario_id": scenario_id,
                    "reasoning_text": "On reflection the artifacts show an unapproved egress and secret risk.",
                },
            )

    assert retried_partial is not None
    client.post(f"/api/sessions/{session_id}/finish-early")
    results = client.get(f"/api/sessions/{session_id}/results").json()
    assert results["rounds_needed_nudge"] >= 1
    retried_rows = [row for row in results["rounds"] if row["retried"]]
    assert retried_rows
    assert retried_rows[0]["retry_verdict"] is not None


def test_retry_survives_legacy_state_without_decision_log(client, test_settings) -> None:
    from blast_radius.storage import SessionStore

    session_id, scenario_id, _ = _answered_wrong_or_partial(client)
    store = SessionStore(test_settings.database_path, test_settings.session_ttl_minutes)
    state = store.get(session_id)
    # Simulate a session answered before decision_log existed.
    state.decision_log = {}
    store.save(state)
    response = client.post(
        f"/api/sessions/{session_id}/rounds/retry",
        json={"scenario_id": scenario_id, "reasoning_text": "Revising after a legacy upgrade path."},
    )
    assert response.status_code == 409


def _complete_demo(client, bank, *, handle=None, correct=True):
    payload = {"mode": "demo"}
    if handle is not None:
        payload["operator_handle"] = handle
    created = client.post("/api/sessions", json=payload).json()
    session_id = created["session_id"]
    pre = assessment_answers(bank, created["pretest"])
    client.post(f"/api/sessions/{session_id}/pretest", json={"answers": pre})
    for _ in range(6):
        round_data = client.post(f"/api/sessions/{session_id}/rounds/next").json()
        scenario_id = round_data["scenario"]["id"]
        if scenario_id == "cmd-cleanup-2":
            body = {
                "scenario_id": scenario_id,
                "action": "sandbox",
                "reasoning_text": "Bound the destructive generated-directory cleanup to the workspace.",
                "blast_radius_config": {
                    "readable_paths": ["/workspace/htmlcov"],
                    "writable_paths": ["/workspace/htmlcov"],
                    "network_enabled": False,
                    "network_allowlist": [],
                    "capabilities": ["delete-generated-files"],
                },
            }
        else:
            body = {
                "scenario_id": scenario_id,
                "action": "reject",
                "reasoning_text": "The artifacts show an unapproved secret, scope, provenance, or egress risk.",
            }
        client.post(f"/api/sessions/{session_id}/decisions", json=body)
    done = client.post(f"/api/sessions/{session_id}/rounds/next").json()
    post = assessment_answers(bank, done["posttest"], incorrect_ids=set() if correct else {q["id"] for q in done["posttest"]})
    client.post(f"/api/sessions/{session_id}/posttest", json={"answers": post})
    return session_id


def test_operator_handle_is_validated(client) -> None:
    assert client.post("/api/sessions", json={"mode": "demo", "operator_handle": "x"}).status_code == 422
    assert client.post("/api/sessions", json={"mode": "demo", "operator_handle": "a" * 41}).status_code == 422
    assert client.post("/api/sessions", json={"mode": "demo", "operator_handle": "no@emails"}).status_code == 422
    ok = client.post("/api/sessions", json={"mode": "demo", "operator_handle": "max-g"})
    assert ok.status_code == 201
    assert ok.json()["operator_handle"] == "max-g"
    # The documented/advertised maximum of exactly 40 characters must be accepted.
    boundary = client.post("/api/sessions", json={"mode": "demo", "operator_handle": "a" * 40})
    assert boundary.status_code == 201


def test_finished_sessions_write_a_durable_team_summary(client, test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    _complete_demo(client, bank, handle="max-g")
    summary = client.get("/api/team/summary").json()
    assert summary["summaries"], "a finished session should produce a summary row"
    row = summary["summaries"][0]
    assert row["operator_handle"] == "max-g"
    assert row["posttest"] is not None
    handles = {entry["handle"] for entry in summary["roster"]}
    assert "max-g" in handles


def test_team_summary_aggregates_anonymous_and_survives_ttl(client, test_settings) -> None:
    bank = ScenarioBank(test_settings.data_dir)
    _complete_demo(client, bank)  # no handle -> anonymous
    _complete_demo(client, bank, handle="dana")
    summary = client.get("/api/team/summary").json()
    handles = {entry["handle"] for entry in summary["roster"]}
    assert "anonymous" in handles
    assert "dana" in handles
    assert "persist beyond" in summary["window"]


def test_drill_never_writes_a_team_summary(client) -> None:
    created = client.post("/api/sessions", json={"mode": "drill"}).json()
    session_id = created["session_id"]
    scenario = client.post(f"/api/sessions/{session_id}/rounds/next").json()["scenario"]
    client.post(
        f"/api/sessions/{session_id}/decisions",
        json={"scenario_id": scenario["id"], "action": "reject", "reasoning_text": "Rejecting this drill request outright."},
    )
    assert client.get("/api/team/summary").json()["summaries"] == []


def _bias_grade(action: str, correct: str):
    from blast_radius.models import GradeResult

    return GradeResult(
        scenario_id="sce-1",
        verdict="wrong" if action != correct else "correct",
        action_correct=action == correct,
        action=action,
        correct_action=correct,
        reasoning_score=0,
        matched_tells=[],
        missed_tells=[],
        receipts=[],
        explanation="x",
        socratic_followup="y",
    )


def test_oversight_bias_classifies_wrong_calls_by_direction() -> None:
    from blast_radius.api import _oversight_bias

    bias = _oversight_bias(
        [
            _bias_grade("approve", "reject"),  # under-contained -> over-approval
            _bias_grade("sandbox", "reject"),  # under-contained -> over-approval
            _bias_grade("reject", "approve"),  # over-contained -> over-restriction
            _bias_grade("reject", "reject"),  # correct
        ]
    )
    assert bias is not None
    assert (bias.over_approval, bias.over_restriction, bias.correct) == (2, 1, 1)
    assert bias.graded_rounds == 4
    assert bias.dominant == "over_approval"
    assert "rubber-stamp" in bias.summary


def test_oversight_bias_is_none_without_recorded_actions() -> None:
    # Grades persisted before the action/correct_action fields existed must not
    # crash or fabricate a tendency — they are simply skipped.
    from blast_radius.api import _oversight_bias
    from blast_radius.models import GradeResult

    legacy = GradeResult(
        scenario_id="sce-1",
        verdict="correct",
        action_correct=True,
        reasoning_score=100,
        matched_tells=[],
        missed_tells=[],
        receipts=[],
        explanation="x",
        socratic_followup="y",
    )
    assert _oversight_bias([legacy]) is None
