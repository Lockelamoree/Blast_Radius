from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from blast_radius.auth import (
    AttemptLimiter,
    issue_token,
    mint_uid_token,
    resolve_uid,
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


def test_uid_token_round_trips_and_rejects_role_tokens() -> None:
    # A signed token is opaque (a base64 cookie value); it resolves back to the
    # full "uid:<hex>" identity, which is the stable per-user key.
    token = mint_uid_token(SECRET)
    resolved = resolve_uid(SECRET, token, max_age_seconds=3600)
    assert resolved is not None and resolved.startswith("uid:")
    assert resolve_uid(SECRET, token, max_age_seconds=3600) == resolved
    # An access-role token pasted into the uid slot must NOT be accepted as an
    # identity (can't adopt a role cookie as a user).
    role_token = issue_token(SECRET, "judge")
    assert resolve_uid(SECRET, role_token, max_age_seconds=3600) is None
    # Tampered, expired, and missing tokens all fail closed.
    assert resolve_uid(SECRET, token + "x", max_age_seconds=3600) is None
    assert resolve_uid("other-secret", token, max_age_seconds=3600) is None
    assert resolve_uid(SECRET, None, max_age_seconds=3600) is None


def test_uid_open_fallback_when_no_secret_configured() -> None:
    # Without a secret (ungated dev / tests) we mint an unsigned uid-open token and
    # accept it verbatim so identity is still stable per browser.
    token = mint_uid_token("")
    assert token.startswith("uid-open:")
    assert resolve_uid("", token, max_age_seconds=3600) == token
    # Junk / oversized values are rejected even in the open fallback.
    assert resolve_uid("", "uid-open:" + "z" * 200, max_age_seconds=3600) is None
    assert resolve_uid("", "not-a-uid", max_age_seconds=3600) is None
    # With a secret configured, an unsigned uid-open token is not accepted.
    assert resolve_uid(SECRET, token, max_age_seconds=3600) is None


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


def _unlock(client: TestClient, code: str) -> None:
    response = client.post(
        "/access", data={"code": code, "next": "/"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert client.cookies.get("br_access")


def test_team_summary_requires_developer_role(auth_settings: Settings) -> None:
    # No cookie -> the middleware 401s /api/* before the handler runs.
    with TestClient(create_app(auth_settings)) as client:
        assert client.get("/api/team/summary").status_code == 401

    # Judge cookie reaches the handler but is downgraded to 403.
    with TestClient(create_app(auth_settings)) as client:
        _unlock(client, "JUDGE-TOKEN-1")
        assert client.get("/api/team/summary").status_code == 403

    # Developer cookie is allowed.
    with TestClient(create_app(auth_settings)) as client:
        _unlock(client, "DEV-TOKEN-2")
        ok = client.get("/api/team/summary")
        assert ok.status_code == 200
        assert "roster" in ok.json()


def test_persistent_profile_works_behind_the_gate(auth_settings: Settings) -> None:
    with TestClient(create_app(auth_settings)) as client:
        # /api/me is gated like the rest of the API until a code is presented.
        assert client.get("/api/me").status_code == 401
        _unlock(client, "JUDGE-TOKEN-1")
        me = client.get("/api/me")
        assert me.status_code == 200
        assert client.cookies.get("br_uid")
        # The leaderboard is open to any code-holder (not developer-only).
        assert client.get("/api/leaderboard").status_code == 200
        # With signing on, a forged uid token cannot be adopted.
        forged = client.post("/api/me/adopt", json={"token": "uid:deadbeef.forged-sig"})
        assert forged.status_code == 401


def test_team_and_author_pages_are_developer_only(auth_settings: Settings) -> None:
    with TestClient(create_app(auth_settings)) as client:
        anon = client.get("/team", follow_redirects=False)
        assert anon.status_code == 303
        assert anon.headers["location"].startswith("/access")

    for path in ("/team", "/author"):
        with TestClient(create_app(auth_settings)) as client:
            _unlock(client, "JUDGE-TOKEN-1")
            assert client.get(path).status_code == 403
        with TestClient(create_app(auth_settings)) as client:
            _unlock(client, "DEV-TOKEN-2")
            assert client.get(path).status_code == 200


def test_screen_page_is_gated_but_open_to_any_code_holder(auth_settings: Settings) -> None:
    with TestClient(create_app(auth_settings)) as client:
        anon = client.get("/screen", follow_redirects=False)
        assert anon.status_code == 303
        assert anon.headers["location"].startswith("/access")
    # Unlike /team and /author (developer-only), /screen admits a JUDGE code too —
    # it backs the any-code-holder POST /api/check.
    for token in ("JUDGE-TOKEN-1", "DEV-TOKEN-2"):
        with TestClient(create_app(auth_settings)) as client:
            _unlock(client, token)
            assert client.get("/screen").status_code == 200


def test_team_views_are_open_when_auth_is_disabled(tmp_path: Path) -> None:
    package_dir = Path(__file__).resolve().parents[1] / "blast_radius"
    open_settings = Settings(
        base_dir=package_dir,
        database_path=tmp_path / "open.db",
        openai_api_key=None,
        live_generation=False,
    )
    with TestClient(create_app(open_settings)) as client:
        assert client.get("/api/team/summary").status_code == 200
        assert client.get("/team").status_code == 200
        assert client.get("/author").status_code == 200
