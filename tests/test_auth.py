from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from blast_radius.auth import (
    AttemptLimiter,
    issue_token,
    verify_token,
)
from blast_radius.config import Settings, parse_access_codes
from blast_radius.main import create_app

SECRET = "unit-test-secret-value"


def test_parse_access_codes_labels_and_ignores_blanks() -> None:
    codes = parse_access_codes(" judge:JUDGE-1 , developer:DEV-2 ,, BARE-3 ")
    assert codes == {"JUDGE-1": "judge", "DEV-2": "developer", "BARE-3": "guest"}
    assert parse_access_codes("") == {}


def test_token_round_trip_and_tamper_resistance() -> None:
    token = issue_token(SECRET, "judge")
    assert verify_token(SECRET, token, max_age_seconds=3600) == "judge"
    # Wrong secret, tampered signature, and garbage all fail closed.
    assert verify_token("other-secret", token, max_age_seconds=3600) is None
    assert verify_token(SECRET, token + "x", max_age_seconds=3600) is None
    assert verify_token(SECRET, "not-a-token", max_age_seconds=3600) is None
    assert verify_token(SECRET, None, max_age_seconds=3600) is None


def test_token_expiry_and_future_dating() -> None:
    token = issue_token(SECRET, "developer", issued_at=1_000)
    assert verify_token(SECRET, token, max_age_seconds=100, now=1_050) == "developer"
    assert verify_token(SECRET, token, max_age_seconds=100, now=1_200) is None
    # Clearly future-dated tokens are rejected (beyond skew tolerance).
    future = issue_token(SECRET, "judge", issued_at=5_000)
    assert verify_token(SECRET, future, max_age_seconds=100, now=1_000) is None


def test_verify_token_fails_closed_on_non_ascii_signature() -> None:
    # A crafted cookie with a high byte in the signature must return None, never
    # raise (hmac.compare_digest would otherwise TypeError, surfacing as a 500).
    assert verify_token(SECRET, "Zm9v.éÿ", max_age_seconds=3600) is None
    assert verify_token(SECRET, "é.YWJj", max_age_seconds=3600) is None


def test_attempt_limiter_blocks_after_threshold_then_expires() -> None:
    limiter = AttemptLimiter(max_attempts=3, window_seconds=60)
    for offset in range(3):
        assert limiter.blocked("ip", now=offset) is False
        limiter.record("ip", now=offset)
    assert limiter.blocked("ip", now=3) is True
    # Once the window slides past the recorded hits, the key clears.
    assert limiter.blocked("ip", now=1_000) is False


def test_attempt_limiter_caps_tracked_keys() -> None:
    # A client rotating identifiers cannot grow the table without bound.
    limiter = AttemptLimiter(max_attempts=3, window_seconds=10_000, max_keys=16)
    for index in range(200):
        limiter.record(f"ip-{index}", now=float(index))
    assert len(limiter._hits) <= 16


@pytest.fixture
def auth_settings(tmp_path: Path) -> Settings:
    package_dir = Path(__file__).resolve().parents[1] / "blast_radius"
    return Settings(
        base_dir=package_dir,
        database_path=tmp_path / "auth.db",
        openai_api_key=None,
        live_generation=False,
        access_codes="judge:JUDGE-TOKEN-1,developer:DEV-TOKEN-2",
        auth_secret=SECRET,
        auth_cookie_secure=False,
    )


def test_auth_is_disabled_without_configuration(tmp_path: Path) -> None:
    package_dir = Path(__file__).resolve().parents[1] / "blast_radius"
    open_settings = Settings(
        base_dir=package_dir,
        database_path=tmp_path / "open.db",
        openai_api_key=None,
        live_generation=False,
    )
    assert open_settings.auth_enabled is False
    with TestClient(create_app(open_settings)) as client:
        assert client.get("/", follow_redirects=False).status_code == 200
        assert client.get("/api/learn").status_code == 200


def test_gate_blocks_unauthenticated_html_and_api(auth_settings: Settings) -> None:
    assert auth_settings.auth_enabled is True
    with TestClient(create_app(auth_settings)) as client:
        landing = client.get("/", follow_redirects=False)
        assert landing.status_code == 303
        assert landing.headers["location"] == "/access?next=/"

        api = client.get("/api/learn")
        assert api.status_code == 401
        assert api.json()["detail"] == "Access code required."

        # Health and static stay open so deploy/uptime and the access page work.
        assert client.get("/healthz").status_code == 200
        assert client.get("/static/styles.css").status_code == 200

        page = client.get("/access")
        assert page.status_code == 200
        assert "Enter your access code" in page.text


def test_valid_codes_unlock_and_wrong_code_is_rejected(auth_settings: Settings) -> None:
    for code in ("JUDGE-TOKEN-1", "DEV-TOKEN-2"):
        with TestClient(create_app(auth_settings)) as client:
            rejected = client.post(
                "/access", data={"code": "nope", "next": "/"}, follow_redirects=False
            )
            assert rejected.status_code == 401
            assert "not recognised" in rejected.text
            assert not client.cookies.get("br_access")

            unlocked = client.post(
                "/access", data={"code": code, "next": "/"}, follow_redirects=False
            )
            assert unlocked.status_code == 303
            assert unlocked.headers["location"] == "/"
            assert client.cookies.get("br_access")

            # Cookie now grants both the HTML app and the API.
            assert client.get("/", follow_redirects=False).status_code == 200
            assert client.get("/api/learn").status_code == 200


def test_logout_clears_access(auth_settings: Settings) -> None:
    with TestClient(create_app(auth_settings)) as client:
        client.post(
            "/access", data={"code": "JUDGE-TOKEN-1", "next": "/"},
            follow_redirects=False,
        )
        assert client.get("/", follow_redirects=False).status_code == 200
        client.post("/logout", follow_redirects=False)
        assert client.get("/", follow_redirects=False).status_code == 303


def test_repeated_wrong_codes_are_throttled_per_client(auth_settings: Settings) -> None:
    with TestClient(create_app(auth_settings)) as client:
        attacker = {"X-Forwarded-For": "203.0.113.7"}
        for _ in range(8):
            rejected = client.post(
                "/access", data={"code": "bad", "next": "/"},
                headers=attacker, follow_redirects=False,
            )
            assert rejected.status_code == 401
        blocked = client.post(
            "/access", data={"code": "bad", "next": "/"},
            headers=attacker, follow_redirects=False,
        )
        assert blocked.status_code == 429
        assert "Too many attempts" in blocked.text
        # A different client IP is untouched by the attacker's failures.
        other = client.post(
            "/access", data={"code": "bad", "next": "/"},
            headers={"X-Forwarded-For": "203.0.113.8"}, follow_redirects=False,
        )
        assert other.status_code == 401


def test_healthz_reports_auth_state(auth_settings: Settings) -> None:
    with TestClient(create_app(auth_settings)) as client:
        assert client.get("/healthz").json()["auth_enabled"] is True


@pytest.mark.parametrize(
    "hostile_next",
    [
        "//evil.example.com/phish",
        "/\\evil.example.com",
        "https://evil.example.com",
        "/legit\r\nSet-Cookie: x=1",
    ],
)
def test_open_redirect_target_is_sanitised(
    auth_settings: Settings, hostile_next: str
) -> None:
    with TestClient(create_app(auth_settings)) as client:
        unlocked = client.post(
            "/access",
            data={"code": "JUDGE-TOKEN-1", "next": hostile_next},
            follow_redirects=False,
        )
        assert unlocked.status_code == 303
        assert unlocked.headers["location"] == "/"
