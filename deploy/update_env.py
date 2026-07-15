"""Atomically update the deployment environment while preserving unknown settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def update_environment(path: Path, app_dir: Path, environ: dict[str, str]) -> None:
    managed = {
        "BLAST_RADIUS_DATABASE": str(app_dir / "blast_radius.db"),
        "BLAST_RADIUS_LIVE_GENERATION": "false",
        "BLAST_RADIUS_SESSION_TTL_MINUTES": "180",
        "BLAST_RADIUS_DAILY_LLM_BUDGET": environ.get(
            "BLAST_RADIUS_DAILY_LLM_BUDGET", "500"
        ),
        "BLAST_RADIUS_CRITIC_TIMEOUT_SECONDS": "8",
    }
    if environ.get("BLAST_RADIUS_UPDATE_OPENAI_KEY") == "1":
        managed["OPENAI_API_KEY"] = environ.get("OPENAI_API_KEY", "")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if line.split("=", 1)[0] not in managed]
    kept.extend(f"{key}={value}" for key, value in managed.items())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(kept) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: update_env.py ENV_FILE APP_DIR")
    update_environment(Path(sys.argv[1]), Path(sys.argv[2]), dict(os.environ))
