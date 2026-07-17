import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_action_yml_is_a_composite_action() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert 'using: "composite"' in action
    assert "${GITHUB_ACTION_PATH}" in action
    assert "action_verify.sh" in action
    assert 'name: "Blast Radius verify"' in action


def test_action_is_marketplace_ready() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    # Marketplace requires a branding block (Feather icon + palette colour).
    assert "branding:" in action
    assert "icon:" in action and "color:" in action
    # A pinned setup-python step guarantees a supported interpreter on any runner.
    assert "actions/setup-python@" in action
    # Marketplace caps the description at 125 characters — enforce it here so a
    # future edit can't silently break publishing.
    match = re.search(r'^description:\s*"(.+)"\s*$', action, re.M)
    assert match, "description must be a single double-quoted line"
    assert len(match.group(1)) < 125


def test_action_verify_script_is_strict_and_calls_the_cli() -> None:
    script = (ROOT / "scripts" / "action_verify.sh").read_text(encoding="utf-8")
    assert script.splitlines()[0].startswith("#!")
    assert "set -euo pipefail" in script
    assert "blastradius verify" in script
    assert "blastradius check --kind diff" in script
    # The screen feeds a readable step summary and exposes step outputs.
    assert "action_summary.py" in script
    assert "--json" in script


def test_action_exposes_screen_outputs() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert "outputs:" in action
    assert "steps.screen.outputs.verdict" in action
    assert "id: screen" in action


def test_action_summary_writes_markdown_and_outputs(tmp_path) -> None:
    import json
    import subprocess

    report = {
        "verdict": "reject-recommended",
        "disclaimer": "Deterministic keyword screen — no model ran.",
        "findings": [
            {"severity": "critical", "label": "Sends data to the network", "category": "unapproved_egress"}
        ],
    }
    summary = tmp_path / "summary.md"
    outputs = tmp_path / "outputs.txt"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "action_summary.py")],
        input=json.dumps(report),
        env={"GITHUB_STEP_SUMMARY": str(summary), "GITHUB_OUTPUT": str(outputs), "PATH": os.environ["PATH"]},
        text=True,
        check=True,
    )
    md = summary.read_text(encoding="utf-8")
    assert "reject-recommended" in md
    assert "unapproved_egress" in md
    out = outputs.read_text(encoding="utf-8")
    assert "verdict=reject-recommended" in out
    assert "critical=1" in out


def test_action_summary_no_ops_on_empty_input(tmp_path) -> None:
    import subprocess

    summary = tmp_path / "summary.md"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "action_summary.py")],
        input="",
        env={"GITHUB_STEP_SUMMARY": str(summary), "PATH": os.environ["PATH"]},
        text=True,
        check=True,
    )
    assert not summary.exists()


def test_ci_runs_the_action_script_syntax_check_and_cli_smoke() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "scripts/action_verify.sh" in ci
    assert "blastradius" in ci and "verify --bank" in ci
