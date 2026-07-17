#!/usr/bin/env python3
"""Format a ``blastradius check --json`` diff report as a GitHub Actions step
summary and step outputs. Reads the JSON report on stdin. No-ops safely on empty
or unparseable input, so it never turns a screen failure into a summary failure."""

from __future__ import annotations

import json
import os
import sys

_ICON = {
    "reject-recommended": "❌",  # cross mark
    "sandbox-recommended": "⚠️",  # warning
    "looks-scoped": "✅",  # check mark
}


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        return 0
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    verdict = report.get("verdict", "unknown")
    findings = report.get("findings", [])
    critical = sum(1 for finding in findings if finding.get("severity") == "critical")
    caution = sum(1 for finding in findings if finding.get("severity") == "caution")

    # Always leave a readable one-liner in the job log.
    print(f"Diff screen: {verdict} ({critical} critical, {caution} caution)")

    lines = [
        "## Blast Radius diff screen",
        f"- {_ICON.get(verdict, '•')} **{verdict}** — {critical} critical, {caution} caution",
    ]
    for finding in findings:
        lines.append(
            f"  - `{finding.get('severity', '')}` {finding.get('label', '')} "
            f"({finding.get('category', '')})"
        )
    disclaimer = report.get("disclaimer", "")
    if disclaimer:
        lines += ["", f"> {disclaimer}"]

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"verdict={verdict}\ncritical={critical}\ncaution={caution}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
