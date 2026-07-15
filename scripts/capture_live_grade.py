"""Capture one real hosted GPT-5.6 reasoning grade as reviewable JSON evidence."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

JsonTransport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]


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
    health = transport(base_url, "/healthz", None)
    if health.get("reasoning_grading") != "live":
        raise RuntimeError(
            "hosted critic is not verified live: "
            f"{health.get('reasoning_grading', 'missing health state')}"
        )

    session = transport(base_url, "/api/sessions", {"mode": "demo"})
    session_id = session["session_id"]
    questions = session["pretest"]
    answers = [0 if question["id"] == "q-package" else 1 for question in questions]
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

    deterministic = grade.get("deterministic_matched_tells", [])
    critic = grade.get("critic_matched_tells", [])
    evidence = {
        "captured_at": datetime.now(UTC).isoformat(),
        "base_url": base_url.rstrip("/"),
        "health": health,
        "scenario": scenario,
        "decision": decision,
        "critic_proof": {
            "model": grade.get("critic_model"),
            "response_id": response_id,
            "deterministic_matched_tells": deterministic,
            "critic_matched_tells": critic,
            "critic_only_tells": [tell for tell in critic if tell not in deterministic],
            "followup": grade.get("socratic_followup"),
        },
        "raw_decision_response": raw_decision_response,
    }
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(response_id))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"live_grade_{safe_id}.json"
    output_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
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
