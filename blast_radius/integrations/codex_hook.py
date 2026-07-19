"""Codex CLI ``PreToolUse`` supervisor hook.

Runs the Blast Radius deterministic red-flag inspector on every proposed Bash
command and DENIES the ones that trip a known agent-security red flag — the same
engine you train against in the game, now guarding a live agent's approval loop.

Honesty holds here exactly as in the game: it never claims a command is safe.
A missing denial only means no known pattern matched, and no model runs. It
fails **open** (allows, with a note on stderr) whenever screening cannot run, so
a broken guardrail never bricks the agent.

Reads the PreToolUse event JSON on stdin and emits the ``hookSpecificOutput``
decision on stdout, per the Codex hook protocol.
"""

from __future__ import annotations

import json
import os
import sys

# Restrictiveness of the inspector's three verdicts, and the deny thresholds that
# BLAST_RADIUS_FAIL_ON selects — mirrors the `blastradius check`/Action semantics.
_RANK = {"looks-scoped": 0, "sandbox-recommended": 1, "reject-recommended": 2}
_THRESHOLD = {"never": 3, "sandbox": 1, "reject": 2}


def _emit(decision: str, reason: str | None = None) -> int:
    output: dict = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
        }
    }
    if reason:
        output["hookSpecificOutput"]["permissionDecisionReason"] = reason
    print(json.dumps(output))
    return 0


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return _emit("allow")  # an unparseable event must never block the agent
    command = str((event.get("tool_input") or {}).get("command", "")).strip()
    if not command:
        return _emit("allow")
    try:
        from blast_radius.engine import custom_rules, inspector

        # Team custom rules from a repo .blastradius.toml, if present (fail-open).
        rules, _ = custom_rules.load_safe(custom_rules.discover())
        report = inspector.inspect_text(command, kind="command", custom=rules)
    except Exception as exc:  # screening unavailable -> fail open, but say why
        print(f"blast-radius: command not screened ({type(exc).__name__})", file=sys.stderr)
        return _emit("allow")

    try:  # fingerprint-only audit trail; never blocks the agent if it fails
        from blast_radius import audit

        audit.record(report, kind="command", source="hook")
    except Exception:  # noqa: BLE001 - auditing must never break the guard
        pass

    fail_on = os.environ.get("BLAST_RADIUS_FAIL_ON", "reject")
    threshold = _THRESHOLD.get(fail_on, 2)
    labels = "; ".join(finding.label for finding in report.findings)
    if _RANK.get(report.verdict, 0) >= threshold:
        reason = f"Blast Radius: {report.verdict}"
        if labels:
            reason += f" — {labels}"
        reason += f". {report.disclaimer}"
        return _emit("deny", reason)
    if labels:
        # Allowed, but surface the caution as coaching (agents show hook stderr).
        print(f"blast-radius caution: {labels}", file=sys.stderr)
    return _emit("allow")


if __name__ == "__main__":
    raise SystemExit(main())
