import asyncio
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
from blast_radius.main import create_app
from blast_radius.models import AssessmentForm, Competency, GateResult

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
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["bank_scenarios"] >= 18
    assert health.json()["reasoning_grading"] == "off"
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


def test_gate_catch_rejects_planted_hallucination_without_leaking_it(client) -> None:
    response = client.get("/api/demo/gate-catch")
    assert response.status_code == 200
    assert response.json() == {"passed": False, "reasons": ["unknown template_ref"]}
    assert "ground_truth" not in response.text


def test_gate_catch_is_rate_limited(client) -> None:
    for _ in range(45):
        assert client.get("/api/demo/gate-catch").status_code == 200
    assert client.get("/api/demo/gate-catch").status_code == 429


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
    ):
        identifiers.append(safety_identifier)
        await asyncio.sleep(0.05)
        return await real_grade(engine, scenario, player_decision)

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


def test_demo_reorders_only_the_verified_deck_by_weakest_competency(
    test_settings, monkeypatch
) -> None:
    async def generation_must_not_run(*args, **kwargs):
        raise AssertionError("demo adaptation must not invoke live generation")

    monkeypatch.setattr(TrustEngine, "next_scenario", generation_must_not_run)
    expected_ids = {
        "cmd-cleanup-2",
        "dep-typo-1",
        "tool-scope-1",
        "diff-exfil-1",
        "context-injection-1",
        "market-egress-1",
    }

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

    assert played[:2] == ["tool-scope-1", "market-egress-1"]
    assert set(played) == expected_ids
    assert len(played) == len(set(played)) == 6


def test_session_creation_has_a_per_ip_limit(test_settings) -> None:
    settings = replace(test_settings, session_create_limit_per_hour=1)
    with TestClient(create_app(settings)) as limited_client:
        assert limited_client.post("/api/sessions", json={"mode": "demo"}).status_code == 201
        blocked = limited_client.post("/api/sessions", json={"mode": "demo"})
    assert blocked.status_code == 429


def test_round_requests_have_a_per_session_cap(test_settings) -> None:
    settings = replace(test_settings, session_round_request_cap=1)
    with TestClient(create_app(settings)) as limited_client:
        session_id = create_started_session(limited_client)
        assert limited_client.post(f"/api/sessions/{session_id}/rounds/next").status_code == 200
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
