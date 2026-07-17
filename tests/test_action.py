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
    # The description stays honest about the diff screen being a heuristic.
    assert "not a proof of safety" in action


def test_action_verify_script_is_strict_and_calls_the_cli() -> None:
    script = (ROOT / "scripts" / "action_verify.sh").read_text(encoding="utf-8")
    assert script.splitlines()[0].startswith("#!")
    assert "set -euo pipefail" in script
    assert "blastradius verify" in script
    assert "blastradius check --kind diff" in script


def test_ci_runs_the_action_script_syntax_check_and_cli_smoke() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "scripts/action_verify.sh" in ci
    assert "blastradius" in ci and "verify --bank" in ci
