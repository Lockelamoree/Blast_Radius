"""``blastradius`` — a deterministic, offline command-line screen for real
agent artifacts, plus a bank/scenario gate verifier.

Runs entirely in-process against the installed package (no server, no auth, no
network, no model). Imports only the engine, never ``blast_radius.main``/``api``,
so it stays light and safe to invoke from a pre-commit hook or CI step.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from blast_radius.engine import inspector
from blast_radius.engine.bank import ScenarioBank
from blast_radius.engine.gate import CorrectnessGate
from blast_radius.models import BlastRadiusConfig, InspectionReport, Scenario

_DATA_DIR = Path(__file__).resolve().parent / "data"
_VERDICT_RANK = {"looks-scoped": 0, "sandbox-recommended": 1, "reject-recommended": 2}
_FAIL_ON_THRESHOLD = {"never": 3, "reject": 2, "sandbox": 1}


def _read_source(positional: str | None, file_option: str | None) -> str:
    if file_option is not None:
        return Path(file_option).read_text(encoding="utf-8")
    if positional is None or positional == "-":
        return sys.stdin.read()
    return positional


def _infer_kind(args: argparse.Namespace, content: str) -> str:
    if args.kind:
        return args.kind
    if args.config:
        return "config"
    if args.diff or content.lstrip().startswith(("diff --git", "--- ", "+++ ")):
        return "diff"
    return "command"


def _render_human(report: InspectionReport) -> None:
    print(f"verdict: {report.verdict}  ({report.method}, {report.graded_by})")
    if report.parsed_as:
        print(f"parsed as: {report.parsed_as}")
    if report.score is not None:
        print(f"blast-radius score: {report.score}/100  (baseline: {report.baseline})")
    if not report.findings:
        print("no known red-flag pattern matched.")
    for finding in report.findings:
        print(f"  [{finding.severity}] {finding.label} ({finding.category})")
        for match in finding.matches:
            print(f"      - {match.matched}: {match.excerpt}")
    if report.policy_deltas:
        for delta in report.policy_deltas:
            if delta.status != "ok":
                print(f"  policy {delta.status}: {delta.dimension} — yours={delta.yours} safe={delta.safe}")
    if report.learn:
        print(f"learn: {report.learn['title']}")
    if report.toolkit:
        print(f"toolkit: {report.toolkit['title']}")
    print(f"\n{report.disclaimer}")


def _cmd_check(args: argparse.Namespace) -> int:
    if args.config:
        config = BlastRadiusConfig.model_validate_json(
            Path(args.config).read_text(encoding="utf-8")
        )
        expected = None
        if args.expected:
            expected = BlastRadiusConfig.model_validate_json(
                Path(args.expected).read_text(encoding="utf-8")
            )
        report = inspector.inspect_config(config, expected)
    else:
        content = _read_source(args.artifact, args.diff)
        kind = _infer_kind(args, content)
        if kind == "config":
            print("error: use --config FILE for config checks", file=sys.stderr)
            return 2
        report = inspector.inspect_text(content, kind=kind)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        _render_human(report)

    threshold = _FAIL_ON_THRESHOLD[args.fail_on]
    return 1 if _VERDICT_RANK[report.verdict] >= threshold else 0


def _cmd_verify(args: argparse.Namespace) -> int:
    bank = ScenarioBank(_DATA_DIR)
    gate = CorrectnessGate(bank)
    if args.bank:
        scenarios = list(bank.scenarios.values())
        failures = 0
        for scenario in scenarios:
            result = gate.verify(scenario)
            if not result.passed:
                failures += 1
                print(f"FAIL {scenario.id}: {'; '.join(result.reasons)}")
        if failures:
            return 1
        print(f"PASS {len(scenarios)} scenario(s) through CorrectnessGate")
        return 0

    failures = 0
    for path in args.scenarios:
        scenario = Scenario.model_validate_json(Path(path).read_text(encoding="utf-8"))
        result = gate.verify(scenario)
        if result.passed:
            print(f"PASS {scenario.id}")
        else:
            failures += 1
            print(f"FAIL {scenario.id}: {'; '.join(result.reasons)}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blastradius",
        description="Deterministic red-flag screen and scenario gate verifier. "
        "No model runs; it cannot prove an artifact is safe.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="screen a command, diff, or sandbox config")
    check.add_argument("artifact", nargs="?", help="artifact text, or '-' for stdin")
    check.add_argument("--kind", choices=["command", "diff", "config"])
    check.add_argument("--config", help="path to a BlastRadiusConfig JSON file")
    check.add_argument("--diff", help="path to a unified-diff file")
    check.add_argument("--expected", help="path to an expected BlastRadiusConfig JSON (config only)")
    check.add_argument("--json", action="store_true", help="emit the full JSON report")
    check.add_argument(
        "--fail-on",
        choices=["reject", "sandbox", "never"],
        default="reject",
        help="exit 1 when the verdict reaches this level (default: reject)",
    )
    check.set_defaults(func=_cmd_check)

    verify = sub.add_parser("verify", help="run the production gate over scenario JSON")
    verify.add_argument("scenarios", nargs="*", help="scenario JSON file(s)")
    verify.add_argument("--bank", action="store_true", help="verify the whole curated bank")
    verify.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "verify" and not args.bank and not args.scenarios:
        parser.error("verify needs scenario file(s) or --bank")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
