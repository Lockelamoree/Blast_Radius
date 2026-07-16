import os
import stat
from pathlib import Path

from deploy.update_env import update_environment


def read_values(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def test_deploy_env_preserves_unset_key_and_updates_managed_values(tmp_path) -> None:
    path = tmp_path / "blast-radius.env"
    path.write_text("OPENAI_API_KEY=old-key\nCUSTOM_SETTING=keep\nBLAST_RADIUS_DAILY_LLM_BUDGET=100\n")

    update_environment(path, Path("/var/lib/blast-radius"), {})

    values = read_values(path)
    assert values["OPENAI_API_KEY"] == "old-key"
    assert values["CUSTOM_SETTING"] == "keep"
    assert values["BLAST_RADIUS_DAILY_LLM_BUDGET"] == "500"
    assert values["BLAST_RADIUS_CRITIC_TIMEOUT_SECONDS"] == "8"
    assert values["BLAST_RADIUS_GENERATION_TIMEOUT_SECONDS"] == "15"
    assert values["BLAST_RADIUS_SESSION_LLM_CALL_CAP"] == "12"
    assert values["BLAST_RADIUS_GENERATED_ROUNDS_PER_SESSION"] == "5"
    assert values["BLAST_RADIUS_LIVE_GENERATION"] == "false"
    assert values["BLAST_RADIUS_GENERATOR_MAX_OUTPUT_TOKENS"] == "2048"
    assert values["BLAST_RADIUS_GENERATION_TIMEOUT_SECONDS"] == "15"
    assert values["BLAST_RADIUS_SESSION_LLM_CALL_CAP"] == "12"
    assert values["BLAST_RADIUS_GENERATED_ROUNDS_PER_SESSION"] == "5"
    assert values["BLAST_RADIUS_GENERATION_BUDGET_RESERVE"] == "60"
    assert values["BLAST_RADIUS_GATE_MAX_OUTPUT_TOKENS"] == "4096"
    assert values["BLAST_RADIUS_REASONING_MAX_OUTPUT_TOKENS"] == "2048"
    assert values["BLAST_RADIUS_ENABLE_DOCS"] == "false"
    assert values["BLAST_RADIUS_REVISION"] == "unknown"
    assert values["BLAST_RADIUS_DATABASE"] == "/var/lib/blast-radius/blast_radius.db"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.glob(".blast-radius.env.*")) == []


def test_deploy_env_records_exact_revision(tmp_path) -> None:
    path = tmp_path / "blast-radius.env"

    update_environment(
        path,
        Path("/var/lib/blast-radius"),
        {"BLAST_RADIUS_REVISION": "abc123def456"},
    )

    assert read_values(path)["BLAST_RADIUS_REVISION"] == "abc123def456"


def test_deploy_env_can_explicitly_enable_live_generation(tmp_path) -> None:
    path = tmp_path / "blast-radius.env"

    update_environment(
        path,
        Path("/var/lib/blast-radius"),
        {"BLAST_RADIUS_LIVE_GENERATION": "true"},
    )

    assert read_values(path)["BLAST_RADIUS_LIVE_GENERATION"] == "true"


def test_deploy_env_replaces_or_clears_explicit_key(tmp_path) -> None:
    path = tmp_path / "blast-radius.env"
    path.write_text("OPENAI_API_KEY=old-key\n")

    update_environment(
        path,
        Path("/var/lib/blast-radius"),
        {"BLAST_RADIUS_UPDATE_OPENAI_KEY": "1", "OPENAI_API_KEY": "new-key"},
    )
    assert read_values(path)["OPENAI_API_KEY"] == "new-key"

    update_environment(
        path,
        Path("/var/lib/blast-radius"),
        {"BLAST_RADIUS_UPDATE_OPENAI_KEY": "1", "OPENAI_API_KEY": ""},
    )
    assert read_values(path)["OPENAI_API_KEY"] == ""


def test_deploy_fails_unverified_grading_without_explicit_override() -> None:
    deploy_dir = Path(__file__).parents[1] / "deploy"
    script = (deploy_dir / "deploy.sh").read_text()
    service = (deploy_dir / "blast-radius.service").read_text()
    assert 'if [[ "$GRADING_STATE" != "live" ]]' in script
    assert "journalctl -u blast-radius.service" in script
    assert "BLAST_RADIUS_ALLOW_DEGRADED_DEPLOY" in script
    assert "caddy validate" in script
    assert "systemctl restart blast-radius.service" in script
    assert 'if [[ "$HEALTH_REVISION" != "$DEPLOY_REVISION" ]]' in script
    assert 'if [[ "$HEALTH_STATUS" != "ok" ]]' in script
    assert 'if [[ "$HEALTH_CRITIC_MODEL" != "gpt-5.6-sol" ]]' in script
    assert 'unset OPENAI_API_KEY' in script
    assert "BLAST_RADIUS_PROMPT_FOR_OPENAI_KEY" in script
    assert "LIVE_GENERATION_VALUE" in script
    assert "BLAST_RADIUS_LIVE_GENERATION must be true or false" in script
    assert "blast-radius-deploy.lock" in script
    assert 'git clone --branch "$BRANCH" --single-branch' in script
    assert 'git -C "$INCOMING_DIR" status --porcelain' in script
    assert '"$RELEASE_DIR/.venv/bin/python" -m pip install "$RELEASE_DIR"' in script
    assert 'chmod -R u=rwX,go=rX "$RELEASE_DIR"' in script
    assert 'runuser -u "$RUNTIME_USER"' in script
    assert "pip install -e" not in script
    assert 'STATE_DIR="/var/lib/blast-radius"' in script
    assert "Python 3.11+" in script
    assert "systemctl stop blast-radius.service\n" in script
    assert "systemctl is-active --quiet blast-radius.service" in script
    assert "systemctl stop blast-radius.service || true" not in script
    assert 'python3 "$RELEASE_DIR/deploy/update_env.py" "$ENV_CANDIDATE"' in script
    assert 'install -m 600 -o root -g root "$ENV_CANDIDATE" "$ENV_FILE"' in script
    assert "restoring the previous trusted configuration" in script
    assert "ROLLBACK FAILED" in script
    assert "Previous trusted deployment restored and verified" in script
    assert "http://127.0.0.1:8000/healthz" in script
    assert '"$candidate" == "$RELEASE_DIR" || "$candidate" == "$PREVIOUS_TARGET"' in script
    assert 'PREVIOUS_TARGET="$(readlink -f "$APP_DIR")"' in script
    assert "WorkingDirectory=/var/lib/blast-radius" in service
    assert "ReadWritePaths=/var/lib/blast-radius" in service
    assert "ReadWritePaths=/opt/blast-radius" not in service
    assert "PYTHONDONTWRITEBYTECODE=1" in service
    assert "UMask=0077" in service
    cutover = script.index('backup_file "$ENV_FILE" env')
    assert script.index("CUTOVER_STARTED=1", cutover) < script.index(
        "systemctl stop blast-radius.service", cutover
    )
    restart = script.index("systemctl restart blast-radius.service", cutover)
    local_poll = script.index(
        "http://127.0.0.1:8000/healthz", restart
    )
    public_poll = script.index('https://$DOMAIN/healthz', local_poll)
    assert restart < local_poll < public_poll
    assert "exit 1" in script
