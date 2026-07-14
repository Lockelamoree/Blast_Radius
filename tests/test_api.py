from dataclasses import replace

from fastapi.testclient import TestClient

from blast_radius.main import create_app


def create_started_session(client):
    created = client.post("/api/sessions", json={"mode": "demo"})
    assert created.status_code == 201
    session_id = created.json()["session_id"]
    pretest = client.post(
        f"/api/sessions/{session_id}/pretest", json={"answers": [0, 0, 0, 0, 0]}
    )
    assert pretest.status_code == 200
    return session_id


def test_health_and_home(client) -> None:
    assert client.get("/").status_code == 200
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["bank_scenarios"] >= 18
    assert "api_key" not in str(health.json()).lower()


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


def test_full_demo_session(client) -> None:
    session_id = create_started_session(client)
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
    post = client.post(
        f"/api/sessions/{session_id}/posttest", json={"answers": [1, 1, 1, 1, 1]}
    )
    assert post.status_code == 200
    result = client.get(f"/api/sessions/{session_id}/results")
    assert result.status_code == 200
    assert result.json()["delta"] == 5
    assert result.json()["rounds_played"] == 6
    assert "pre 0/5 → post 5/5" in result.json()["share_text"]


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
