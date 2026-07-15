import json

import pytest

from scripts.capture_live_grade import capture_live_grade


class FakeHostedInstance:
    def __init__(self, critic_used: bool = True):
        self.critic_used = critic_used
        self.calls = []

    def __call__(self, base_url, path, payload):
        self.calls.append((path, payload))
        if path == "/healthz":
            return {
                "status": "ok",
                "reasoning_grading": "live",
                "critic_model": "gpt-5.6-sol",
                "live_generation": False,
            }
        if path == "/api/sessions":
            return {
                "session_id": "session-test",
                "pretest": [
                    {"id": "q-command"},
                    {"id": "q-package"},
                    {"id": "q-manifest"},
                    {"id": "q-diff"},
                    {"id": "q-context"},
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
                    "critic_model": "gpt-5.6-sol" if self.critic_used else None,
                    "critic_response_id": "resp_live_123" if self.critic_used else None,
                    "graded_by": "gpt-5.6-sol" if self.critic_used else "deterministic",
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
    assert evidence["critic_proof"]["deterministic_matched_tells"] == []
    assert evidence["critic_proof"]["critic_only_tells"] == [
        "near-miss package name"
    ]
    pretest = next(payload for path, payload in hosted.calls if path.endswith("/pretest"))
    assert pretest["answers"] == [1, 0, 1, 1, 1]


def test_capture_refuses_deterministic_fallback(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="no evidence written"):
        capture_live_grade(
            "https://blast.example",
            tmp_path,
            FakeHostedInstance(critic_used=False),
        )
    assert list(tmp_path.iterdir()) == []
