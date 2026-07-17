from fastapi.testclient import TestClient


def _start_drill(client: TestClient, **extra) -> dict:
    response = client.post("/api/sessions", json={"mode": "drill", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_drill_session_has_one_round_and_no_pretest(client: TestClient) -> None:
    body = _start_drill(client)
    assert body["mode"] == "drill"
    assert body["rounds_total"] == 1
    assert body["pretest"] == []


def test_drill_round_needs_no_pretest_and_grades(client: TestClient) -> None:
    session = _start_drill(client)["session_id"]
    nxt = client.post(f"/api/sessions/{session}/rounds/next", json={})
    assert nxt.status_code == 200
    data = nxt.json()
    assert data["complete"] is False
    assert data["provenance"] == "verified"
    scenario = data["scenario"]

    decision = client.post(
        f"/api/sessions/{session}/decisions",
        json={
            "scenario_id": scenario["id"],
            "action": "reject",
            "reasoning_text": "This looks like a dangerous exfiltration attempt to me.",
        },
    )
    assert decision.status_code == 200
    body = decision.json()
    assert body["rounds_remaining"] == 0
    assert "drill" in body
    assert body["drill"]["share_text"].startswith("Daily Blast Radius drill:")

    done = client.post(f"/api/sessions/{session}/rounds/next", json={})
    assert done.json() == {"complete": True, "drill_complete": True}


def test_drill_rejects_assessments_and_results(client: TestClient) -> None:
    session = _start_drill(client)["session_id"]
    assert client.post(f"/api/sessions/{session}/pretest", json={"answers": [0, 0, 0, 0, 0]}).status_code == 409
    assert client.post(f"/api/sessions/{session}/posttest", json={"answers": [0, 0, 0, 0, 0]}).status_code == 409
    assert client.get(f"/api/sessions/{session}/results").status_code == 409


def test_same_client_key_and_day_is_deterministic(client: TestClient) -> None:
    first = _start_drill(client, client_key="stable-client-01")
    second = _start_drill(client, client_key="stable-client-01")

    def scenario_id(session_id: str) -> str:
        return client.post(f"/api/sessions/{session_id}/rounds/next", json={}).json()["scenario"]["id"]

    assert scenario_id(first["session_id"]) == scenario_id(second["session_id"])


def test_family_pin_serves_that_family(client: TestClient) -> None:
    session = _start_drill(client, family="poisoned_dependency", client_key="fam-client-1")["session_id"]
    data = client.post(f"/api/sessions/{session}/rounds/next", json={}).json()
    assert data["scenario"]["family"] == "poisoned_dependency"


def test_drill_rejects_coached_retry(client: TestClient) -> None:
    session = _start_drill(client)["session_id"]
    scenario = client.post(f"/api/sessions/{session}/rounds/next", json={}).json()["scenario"]
    client.post(
        f"/api/sessions/{session}/decisions",
        json={
            "scenario_id": scenario["id"],
            "action": "approve",
            "reasoning_text": "Approving this without much scrutiny for the test.",
        },
    )
    # The revise/retry path is not offered in drills and the endpoint refuses it.
    retry = client.post(
        f"/api/sessions/{session}/rounds/retry",
        json={"scenario_id": scenario["id"], "reasoning_text": "Reconsidering my reasoning here."},
    )
    assert retry.status_code == 409


def test_drill_option_validation(client: TestClient) -> None:
    # Unknown family -> 422
    assert client.post("/api/sessions", json={"mode": "drill", "family": "nonsense"}).status_code == 422
    # drill-only fields on a demo session -> 422
    assert client.post("/api/sessions", json={"mode": "demo", "family": "poisoned_dependency"}).status_code == 422
    assert client.post("/api/sessions", json={"mode": "demo", "client_key": "abcdefgh"}).status_code == 422
    # bad client_key pattern -> 422
    assert client.post("/api/sessions", json={"mode": "drill", "client_key": "no"}).status_code == 422
