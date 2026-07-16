from __future__ import annotations

import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


SCENARIOS_PATH = (
    Path(__file__).resolve().parents[1] / "blast_radius" / "data" / "scenarios.json"
)
TIMEOUT_SECONDS = 10
USER_AGENT = "Blast-Radius-Evidence-Link-Check/1.0"


@dataclass(frozen=True)
class ProbeResult:
    method: str
    status: int | None
    redirects: tuple[tuple[int, str, str], ...]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class RedirectTracker(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirects: list[tuple[int, str, str]] = []

    def redirect_request(
        self,
        request: Request,
        file_pointer,
        code: int,
        message: str,
        headers,
        new_url: str,
    ) -> Request | None:
        self.redirects.append((code, request.full_url, new_url))
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def load_sources(path: Path = SCENARIOS_PATH) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        scenarios = json.load(handle)
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios.json must contain a non-empty list")

    sources: set[str] = set()
    for scenario in scenarios:
        scenario_id = scenario.get("id", "<unknown>")
        evidence = scenario.get("ground_truth", {}).get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{scenario_id} has no evidence records")
        for record in evidence:
            source = record.get("source") if isinstance(record, dict) else None
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f"{scenario_id} has an evidence record without a source")
            sources.add(source)
    return sorted(sources)


def probe(url: str, method: str) -> ProbeResult:
    tracker = RedirectTracker()
    opener = build_opener(tracker)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    if method == "GET":
        headers["Range"] = "bytes=0-1023"
    request = Request(url, headers=headers, method=method)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            if method == "GET":
                response.read(1024)
            return ProbeResult(
                method=method,
                status=int(response.status),
                redirects=tuple(tracker.redirects),
            )
    except HTTPError as exc:
        return ProbeResult(
            method=method,
            status=exc.code,
            redirects=tuple(tracker.redirects),
            error=str(exc.reason),
        )
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return ProbeResult(
            method=method,
            status=None,
            redirects=tuple(tracker.redirects),
            error=" ".join(str(reason).split()),
        )


def describe_failure(result: ProbeResult) -> str:
    if result.redirects:
        chain = " -> ".join(
            f"{code} {destination}" for code, _source, destination in result.redirects
        )
        return f"redirected ({chain})"
    if result.status is not None:
        return f"{result.method} returned HTTP {result.status}"
    return f"{result.method} failed: {result.error or 'unknown network error'}"


def check_url(url: str) -> tuple[bool, str]:
    head = probe(url, "HEAD")
    if head.redirects:
        return False, describe_failure(head)
    if head.ok:
        return True, f"HTTP {head.status}"

    get = probe(url, "GET")
    if get.redirects:
        return False, describe_failure(get)
    if get.ok:
        return True, f"HTTP {get.status} (GET fallback)"
    return False, f"{describe_failure(head)}; {describe_failure(get)}"


def main() -> int:
    try:
        sources = load_sources()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[FAIL] unable to load evidence sources: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for source in sources:
        ok, detail = check_url(source)
        label = "OK" if ok else "FAIL"
        print(f"[{label}] {detail} {source}")
        failures += not ok

    print(f"Checked {len(sources)} distinct evidence source(s); failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
