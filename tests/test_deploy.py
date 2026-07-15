from pathlib import Path

from deploy.update_env import update_environment


def read_values(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def test_deploy_env_preserves_unset_key_and_updates_managed_values(tmp_path) -> None:
    path = tmp_path / "blast-radius.env"
    path.write_text("OPENAI_API_KEY=old-key\nCUSTOM_SETTING=keep\nBLAST_RADIUS_DAILY_LLM_BUDGET=100\n")

    update_environment(path, Path("/opt/blast-radius"), {})

    values = read_values(path)
    assert values["OPENAI_API_KEY"] == "old-key"
    assert values["CUSTOM_SETTING"] == "keep"
    assert values["BLAST_RADIUS_DAILY_LLM_BUDGET"] == "500"
    assert values["BLAST_RADIUS_CRITIC_TIMEOUT_SECONDS"] == "8"


def test_deploy_env_replaces_or_clears_explicit_key(tmp_path) -> None:
    path = tmp_path / "blast-radius.env"
    path.write_text("OPENAI_API_KEY=old-key\n")

    update_environment(
        path,
        Path("/opt/blast-radius"),
        {"BLAST_RADIUS_UPDATE_OPENAI_KEY": "1", "OPENAI_API_KEY": "new-key"},
    )
    assert read_values(path)["OPENAI_API_KEY"] == "new-key"

    update_environment(
        path,
        Path("/opt/blast-radius"),
        {"BLAST_RADIUS_UPDATE_OPENAI_KEY": "1", "OPENAI_API_KEY": ""},
    )
    assert read_values(path)["OPENAI_API_KEY"] == ""


def test_deploy_fails_unverified_grading_without_explicit_override() -> None:
    script = (Path(__file__).parents[1] / "deploy" / "deploy.sh").read_text()
    assert 'if [[ "$GRADING_STATE" != "live" ]]' in script
    assert "journalctl -u blast-radius.service" in script
    assert "BLAST_RADIUS_ALLOW_DEGRADED_DEPLOY" in script
    assert "exit 1" in script
