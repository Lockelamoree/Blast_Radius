"""Capture one real hosted GPT-5.6 reasoning grade as reviewable JSON evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

JsonTransport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]

PRETEST_CORRECT_OPTIONS = {
    "q-command": "Path scope and reversibility",
    "q-package": "Verify registry provenance and package history",
    "q-manifest": "Its capabilities exceed its stated job",
    "q-diff": "The behavior is absent from the change description",
    "q-context": "As untrusted content and rejected",
}
EXPECTED_CRITIC_MODEL = "gpt-5.6-sol"
_BANNED_EVIDENCE_KEYS = {
    "api_key",
    "authorization",
    "ground_truth",
    "openai_api_key",
    "prompt",
}


def is_expected_critic_model(value: Any) -> bool:
    return isinstance(value, str) and (
        value == EXPECTED_CRITIC_MODEL or value.startswith(f"{EXPECTED_CRITIC_MODEL}-")
    )


def audit_session_hash(session_id: str) -> str:
    return hashlib.sha256(f"blast-radius-audit:v1:{session_id}".encode()).hexdigest()


def assert_safe_evidence(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in _BANNED_EVIDENCE_KEYS:
                raise RuntimeError(f"refusing to write private evidence field: {key}")
            assert_safe_evidence(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_safe_evidence(nested)
    elif isinstance(value, str):
        if re.search(r"\bsk-[A-Za-z0-9_-]{8,}\b", value) or re.search(
            r"(?i)\bBearer\s+[^\s,;]+", value
        ):
            raise RuntimeError("refusing to write a secret-like value to evidence")


def request_json(base_url: str, path: str, payload: dict[str, Any] | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        urljoin(base_url.rstrip("/") + "/", path.lstrip("/")),
        data=body,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json", "User-Agent": "blast-radius-proof/1"},
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - operator-supplied URL
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"{path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"could not reach deployed instance: {exc.reason}") from exc


def capture_live_grade(
    base_url: str,
    output_dir: Path,
    transport: JsonTransport = request_json,
) -> Path:
    parsed_base_url = urlsplit(base_url)
    if (
        parsed_base_url.scheme != "https"
        or not parsed_base_url.netloc
        or parsed_base_url.username
        or parsed_base_url.password
    ):
        raise RuntimeError("proof capture requires a public HTTPS base URL without credentials")
    health = transport(base_url, "/healthz", None)
    if health.get("reasoning_grading") != "live":
        raise RuntimeError(
            "hosted critic is not verified live: "
            f"{health.get('reasoning_grading', 'missing health state')}"
        )
    revision = health.get("revision")
    if not revision or revision in {"unknown", "dev"}:
        raise RuntimeError("hosted instance does not report a deployed Git revision")
    if health.get("live_generation") is not False:
        raise RuntimeError("proof capture requires deterministic public scenario selection")
    if health.get("bank_scenarios") != 18:
        raise RuntimeError("hosted instance does not report the 18-scenario verified bank")
    if health.get("critic_model") != EXPECTED_CRITIC_MODEL:
        raise RuntimeError("hosted instance does not report the expected Sol critic")

    session = transport(base_url, "/api/sessions", {"mode": "demo"})
    session_id = session["session_id"]
    questions = session["pretest"]
    answers = []
    for question in questions:
        question_id = question.get("id")
        correct_option = PRETEST_CORRECT_OPTIONS.get(question_id)
        options = question.get("options", [])
        if not correct_option or correct_option not in options:
            raise RuntimeError(f"unexpected pre-test question: {question_id}")
        if question_id == "q-package":
            answers.append(
                next(
                    index
                    for index, option in enumerate(options)
                    if option != correct_option
                )
            )
        else:
            answers.append(options.index(correct_option))
    transport(base_url, f"/api/sessions/{session_id}/pretest", {"answers": answers})
    round_payload = transport(base_url, f"/api/sessions/{session_id}/rounds/next", {})
    scenario = round_payload["scenario"]
    if scenario.get("id") != "dep-typo-1":
        raise RuntimeError(f"expected dep-typo-1, received {scenario.get('id')}")

    decision = {
        "scenario_id": scenario["id"],
        "action": "reject",
        "reasoning_text": (
            "The proposed library name differs by transposed letters from the dependency "
            "our project normally uses, and its origin has not been established."
        ),
    }
    raw_decision_response = transport(
        base_url,
        f"/api/sessions/{session_id}/decisions",
        decision,
    )
    grade = raw_decision_response["grade"]
    response_id = grade.get("critic_response_id")
    if not grade.get("critic_used") or not response_id or response_id == "unavailable":
        raise RuntimeError("decision fell back to deterministic grading; no evidence written")
    provider_model = grade.get("critic_model")
    if (
        not is_expected_critic_model(provider_model)
        or grade.get("graded_by") != provider_model
        or not str(response_id).startswith("resp_")
    ):
        raise RuntimeError("decision did not return verifiable Sol critic metadata")

    deterministic = grade.get("deterministic_matched_tells", [])
    critic = grade.get("critic_matched_tells", [])
    evidence = {
        "receipt_kind": "application_receipt",
        "captured_at": datetime.now(UTC).isoformat(),
        "base_url": base_url.rstrip("/"),
        "deployment_revision": revision,
        "session_sha256": audit_session_hash(session_id),
        "health": health,
        "scenario": scenario,
        "decision": decision,
        "critic_proof": {
            "requested_model": health.get("critic_model"),
            "provider_model": provider_model,
            "response_id": response_id,
            "deterministic_matched_tells": deterministic,
            "critic_matched_tells": critic,
            "critic_only_tells": [tell for tell in critic if tell not in deterministic],
            "followup": grade.get("socratic_followup"),
        },
        "raw_decision_response": raw_decision_response,
    }
    canonical_receipt = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    evidence["application_receipt_sha256"] = hashlib.sha256(canonical_receipt).hexdigest()
    assert_safe_evidence(evidence)
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(response_id))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"live_grade_{safe_id}.json"
    try:
        with output_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(evidence, indent=2) + "\n")
    except FileExistsError as exc:
        raise RuntimeError(f"refusing to overwrite existing evidence: {output_path}") from exc
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Public HTTPS Blast Radius base URL")
    parser.add_argument("--output-dir", type=Path, default=Path("evidence"))
    args = parser.parse_args()
    output = capture_live_grade(args.base_url, args.output_dir)
    print(output)


if __name__ == "__main__":
    main()
