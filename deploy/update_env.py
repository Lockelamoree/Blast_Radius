"""Atomically update the deployment environment while preserving unknown settings."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def update_environment(path: Path, state_dir: Path, environ: dict[str, str]) -> None:
    managed = {
        "BLAST_RADIUS_DATABASE": f"{state_dir.as_posix().rstrip('/')}/blast_radius.db",
        "BLAST_RADIUS_LIVE_GENERATION": environ.get(
            "BLAST_RADIUS_LIVE_GENERATION", "false"
        ),
        "BLAST_RADIUS_ENABLE_DOCS": "false",
        "BLAST_RADIUS_SESSION_TTL_MINUTES": "180",
        "BLAST_RADIUS_DAILY_LLM_BUDGET": environ.get(
            "BLAST_RADIUS_DAILY_LLM_BUDGET", "500"
        ),
        "BLAST_RADIUS_CRITIC_TIMEOUT_SECONDS": "8",
        "BLAST_RADIUS_GENERATION_TIMEOUT_SECONDS": environ.get(
            "BLAST_RADIUS_GENERATION_TIMEOUT_SECONDS", "15"
        ),
        "BLAST_RADIUS_SESSION_LLM_CALL_CAP": environ.get(
            "BLAST_RADIUS_SESSION_LLM_CALL_CAP", "12"
        ),
        "BLAST_RADIUS_GENERATED_ROUNDS_PER_SESSION": environ.get(
            "BLAST_RADIUS_GENERATED_ROUNDS_PER_SESSION", "5"
        ),
        "BLAST_RADIUS_GENERATION_BUDGET_RESERVE": environ.get(
            "BLAST_RADIUS_GENERATION_BUDGET_RESERVE", "60"
        ),
        "BLAST_RADIUS_GENERATOR_MAX_OUTPUT_TOKENS": environ.get(
            "BLAST_RADIUS_GENERATOR_MAX_OUTPUT_TOKENS", "2048"
        ),
        "BLAST_RADIUS_GATE_MAX_OUTPUT_TOKENS": "4096",
        "BLAST_RADIUS_REASONING_MAX_OUTPUT_TOKENS": "2048",
        "BLAST_RADIUS_REVISION": environ.get("BLAST_RADIUS_REVISION", "unknown"),
    }
    if environ.get("BLAST_RADIUS_UPDATE_OPENAI_KEY") == "1":
        managed["OPENAI_API_KEY"] = environ.get("OPENAI_API_KEY", "")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if line.split("=", 1)[0] not in managed]
    kept.extend(f"{key}={value}" for key, value in managed.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(kept) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: update_env.py ENV_FILE STATE_DIR")
    update_environment(Path(sys.argv[1]), Path(sys.argv[2]), dict(os.environ))
