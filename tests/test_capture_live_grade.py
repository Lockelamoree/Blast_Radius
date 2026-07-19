import hashlib
import json

import pytest

from scripts import capture_live_grade as capture_module
from scripts.capture_live_grade import capture_live_grade, make_json_transport


class _FakeResponse:
    def __init__(self, body: bytes = b"{}"):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingOpener:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def open(self, request, timeout=None):
        self.calls.append((request.get_method(), request.full_url))
        if request.full_url.endswith("/access"):
            return _FakeResponse(b"redirected")
        if request.full_url.endswith("/healthz"):
            return _FakeResponse(b'{"status": "ok"}')
        return _FakeResponse(b"{}")


def test_transport_authenticates_through_the_access_gate_once(monkeypatch) -> None:
    opener = _RecordingOpener()
    monkeypatch.setattr(capture_module, "build_opener", lambda *a, **k: opener)

    transport = make_json_transport("BR-DEV-EXAMPLE")
    assert transport("https://blast.example", "/healthz", None) == {"status": "ok"}

    # The very first network action authenticates (POST /access) before /healthz.
    assert opener.calls[0] == ("POST", "https://blast.example/access")
    assert opener.calls[1][1] == "https://blast.example/healthz"

    # A subsequent call reuses the cookie and does not re-authenticate.
    transport("https://blast.example", "/api/learn", None)
    assert sum(1 for _, url in opener.calls if url.endswith("/access")) == 1


def test_transport_without_a_code_never_hits_the_access_gate(monkeypatch) -> None:
    opener = _RecordingOpener()
    monkeypatch.setattr(capture_module, "build_opener", lambda *a, **k: opener)

    make_json_transport(None)("https://blast.example", "/healthz", None)
    assert all(not url.endswith("/access") for _, url in opener.calls)


class FakeHostedInstance:
    def __init__(
        self,
        critic_used: bool = True,
        *,
        health_model: str = "gpt-5.6-sol",
        grade_model: str = "gpt-5.6-sol",
        response_id: str = "resp_live_123",
    ):
        self.critic_used = critic_used
        self.health_model = health_model
        self.grade_model = grade_model
        self.response_id = response_id
        self.calls = []

    def __call__(self, base_url, path, payload):
        self.calls.append((path, payload))
        if path == "/healthz":
            return {
                "status": "ok",
                "reasoning_grading": "live",
                "critic_model": self.health_model,
                "live_generation": True,
                "bank_scenarios": 20,
                "revision": "abc123def456",
            }
        if path == "/api/sessions":
            return {
                "session_id": "session-test",
                "pretest": [
                    {
                        "id": "q-command",
                        "options": ["noise", "Path scope and reversibility"],
                    },
                    {
                        "id": "q-package",
                        "options": [
                            "Verify registry provenance and package history",
                            "unsafe",
                        ],
                    },
                    {
                        "id": "q-manifest",
                        "options": [
                            "noise",
                            "Its capabilities exceed its stated job",
                        ],
                    },
                    {
                        "id": "q-diff",
                        "options": [
                            "The behavior is absent from the change description",
                            "noise",
                        ],
                    },
                    {
                        "id": "q-context",
                        "options": [
                            "noise",
                            "As untrusted content and rejected",
                        ],
                    },
                ],
            }
        if path.endswith("/pretest"):
            return {"score": 4, "total": 5}
        if path.endswith("/rounds/next"):
            return {
                "scenario": {
                    "id": "dep-typo-1",
                    "family": "poisoned_dependency",
                    "presentation": {"ask_text": "Review this dependency."},
                }
            }
        if path.endswith("/decisions"):
            return {
                "grade": {
                    "critic_used": self.critic_used,
                    "critic_model": self.grade_model if self.critic_used else None,
                    "critic_response_id": self.response_id if self.critic_used else None,
                    "graded_by": self.grade_model if self.critic_used else "deterministic",
                    "deterministic_matched_tells": [],
                    "critic_matched_tells": ["near-miss package name"],
                    "socratic_followup": "Which supplied artifact shows the name mismatch?",
                    "receipts": [{"claim": "verified", "source": "https://example.com"}],
                },
                "rounds_remaining": 5,
            }
        raise AssertionError(path)


def test_capture_writes_real_response_id_and_side_by_side_matches(tmp_path) -> None:
    hosted = FakeHostedInstance()

    output = capture_live_grade("https://blast.example", tmp_path, hosted)
    evidence = json.loads(output.read_text())

    assert output.name == "live_grade_resp_live_123.json"
    assert evidence["critic_proof"]["response_id"] == "resp_live_123"
    assert evidence["response_id"] == "resp_live_123"
    assert evidence["environment"] == "hosted"
    assert evidence["critic_proof"]["requested_model"] == "gpt-5.6-sol"
    assert evidence["critic_proof"]["provider_model"] == "gpt-5.6-sol"
    assert evidence["receipt_kind"] == "application_receipt"
    assert len(evidence["session_sha256"]) == 64
    receipt_hash = evidence.pop("application_receipt_sha256")
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    assert receipt_hash == hashlib.sha256(canonical).hexdigest()
    assert evidence["deployment_revision"] == "abc123def456"
    assert evidence["critic_proof"]["deterministic_matched_tells"] == []
    assert evidence["critic_proof"]["critic_only_tells"] == [
        "near-miss package name"
    ]
    pretest = next(payload for path, payload in hosted.calls if path.endswith("/pretest"))
    assert pretest["answers"] == [1, 1, 1, 0, 1]


def test_capture_accepts_provider_returned_sol_snapshot_name(tmp_path) -> None:
    hosted = FakeHostedInstance(grade_model="gpt-5.6-sol-2026-07-01")

    output = capture_live_grade("https://blast.example", tmp_path, hosted)
    evidence = json.loads(output.read_text())

    assert evidence["critic_proof"]["provider_model"] == "gpt-5.6-sol-2026-07-01"


def test_capture_never_overwrites_an_existing_response_receipt(tmp_path) -> None:
    hosted = FakeHostedInstance()
    output = capture_live_grade("https://blast.example", tmp_path, hosted)
    original = output.read_bytes()

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        capture_live_grade("https://blast.example", tmp_path, hosted)

    assert output.read_bytes() == original


@pytest.mark.parametrize(
    ("leak_key", "leak_value", "error"),
    [
        ("ground_truth", {"correct_action": "reject"}, "private evidence field"),
        ("debug", "sk-" + "proj-should-never-be-written", "secret-like value"),
    ],
)
def test_capture_refuses_private_or_secret_like_evidence(
    tmp_path, leak_key, leak_value, error
) -> None:
    hosted = FakeHostedInstance()

    def leaking_transport(base_url, path, payload):
        result = hosted(base_url, path, payload)
        if path.endswith("/decisions"):
            result["grade"][leak_key] = leak_value
        return result

    with pytest.raises(RuntimeError, match=error):
        capture_live_grade("https://blast.example", tmp_path, leaking_transport)

    assert list(tmp_path.iterdir()) == []


def test_capture_refuses_deterministic_fallback(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="no evidence written"):
        capture_live_grade(
            "https://blast.example",
            tmp_path,
            FakeHostedInstance(critic_used=False),
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "hosted",
    [
        FakeHostedInstance(health_model="gpt-5.6-unexpected"),
        FakeHostedInstance(grade_model="gpt-5.6-unexpected"),
        FakeHostedInstance(response_id="made-up-id"),
    ],
)
def test_capture_refuses_mismatched_or_unverifiable_critic_metadata(
    tmp_path, hosted
) -> None:
    with pytest.raises(RuntimeError):
        capture_live_grade("https://blast.example", tmp_path, hosted)
    assert list(tmp_path.iterdir()) == []


def test_capture_requires_https_before_contacting_host(tmp_path) -> None:
    hosted = FakeHostedInstance()

    with pytest.raises(RuntimeError, match="public HTTPS"):
        capture_live_grade("http://blast.example", tmp_path, hosted)

    assert hosted.calls == []
