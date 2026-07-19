"""Audit the local submission bundle and optionally compare it with deployed health.

The default run is offline. Human-only gaps (video, final captures, dirty worktree)
are warnings; use ``--strict`` to make them blocking immediately before submission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ("screen_decision.png", "screen_verdict.png", "screen_results.png")


@dataclass(frozen=True)
class Check:
    name: str
    status: Literal["pass", "warn", "fail"]
    detail: str


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


def _documentation_check(root: Path) -> Check:
    paths = (root / "README.md", root / "04_PITCH_AND_VIDEO.md", root / "16_DEVPOST_FINAL_COPY.md")
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    stale = [
        token
        for token in (
            "409 tests passed",
            "409-test suite",
            "eighteen-scenario",
            "all eighteen scenarios",
            "18 scenarios",
        )
        if token in text
    ]
    if stale:
        return Check("judge-copy", "fail", f"stale claims remain: {', '.join(stale)}")
    return Check(
        "judge-copy", "pass", "scenario and test-suite claims contain no known stale values"
    )


def _gallery_check(root: Path) -> Check:
    paths = [root / "assets" / name for name in GALLERY]
    missing = [path.name for path in paths if not path.exists()]
    if missing:
        return Check("gallery", "fail", f"missing gallery assets: {', '.join(missing)}")
    try:
        dimensions = {path.name: _png_dimensions(path) for path in paths}
    except ValueError as error:
        return Check("gallery", "fail", str(error))
    wrong_size = [name for name, size in dimensions.items() if size != (1200, 800)]
    if wrong_size:
        return Check("gallery", "warn", f"not 1200x800: {', '.join(wrong_size)}")
    digests = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    if len(set(digests)) != len(digests):
        return Check(
            "gallery",
            "warn",
            "gallery contains duplicate images; capture three distinct live states",
        )
    return Check("gallery", "pass", "three distinct 1200x800 PNG assets are present")


def _video_check(root: Path) -> Check:
    text = (root / "16_DEVPOST_FINAL_COPY.md").read_text(encoding="utf-8")
    if "VIDEO URL — ADD AFTER RECORDING" in text:
        return Check("public-video", "warn", "replace the public-video placeholder after recording")
    if "youtube.com/" not in text and "youtu.be/" not in text:
        return Check("public-video", "warn", "no public YouTube URL found in Devpost copy")
    return Check("public-video", "pass", "public YouTube URL is present")


def _scenario_check(root: Path) -> Check:
    payload = json.loads(
        (root / "blast_radius" / "data" / "scenarios.json").read_text(encoding="utf-8")
    )
    count = len(payload)
    status: Literal["pass", "fail"] = "pass" if count == 20 else "fail"
    return Check("scenario-bank", status, f"{count} scenarios (expected 20)")


def _worktree_check(root: Path) -> Check:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return Check("worktree", "fail", result.stderr.strip() or "git status failed")
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    if changed:
        return Check("worktree", "warn", f"{len(changed)} uncommitted path(s)")
    return Check("worktree", "pass", "clean")


def _revision(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def _health_check(url: str, expected_revision: str) -> Check:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - explicit user URL
            payload = json.load(response)
    except Exception as error:  # noqa: BLE001 - report network/JSON failures uniformly
        return Check("deployed-health", "fail", f"could not read {url}: {error}")
    mismatches: list[str] = []
    if payload.get("status") != "ok":
        mismatches.append(f"status={payload.get('status')!r}")
    if payload.get("bank_scenarios") != 20:
        mismatches.append(f"bank_scenarios={payload.get('bank_scenarios')!r}")
    if payload.get("revision") != expected_revision:
        mismatches.append(f"revision={payload.get('revision')!r}, expected={expected_revision!r}")
    if mismatches:
        return Check("deployed-health", "fail", "; ".join(mismatches))
    return Check("deployed-health", "pass", f"healthy at revision {expected_revision}")


def run_checks(
    root: Path = ROOT,
    *,
    health_url: str | None = None,
    expected_revision: str | None = None,
) -> list[Check]:
    checks = [
        _scenario_check(root),
        _documentation_check(root),
        _gallery_check(root),
        _video_check(root),
        _worktree_check(root),
    ]
    if health_url:
        checks.append(_health_check(health_url, expected_revision or _revision(root)))
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit the Blast Radius submission bundle")
    parser.add_argument("--health-url", help="optional deployed /healthz URL")
    parser.add_argument("--expected-revision", help="expected deployed revision (default: HEAD)")
    parser.add_argument(
        "--strict", action="store_true", help="treat human-pending warnings as failures"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks = run_checks(
        health_url=args.health_url,
        expected_revision=args.expected_revision,
    )
    if args.json:
        print(json.dumps({"checks": [asdict(check) for check in checks]}, indent=2))
    else:
        icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
        for check in checks:
            print(f"[{icons[check.status]}] {check.name}: {check.detail}")
    blocked = any(check.status == "fail" for check in checks)
    warned = any(check.status == "warn" for check in checks)
    return 1 if blocked or (args.strict and warned) else 0


if __name__ == "__main__":
    raise SystemExit(main())
