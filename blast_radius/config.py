from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_dir: Path = Path(__file__).resolve().parent
    database_path: Path = Path(os.getenv("BLAST_RADIUS_DATABASE", "blast_radius.db"))
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    live_generation: bool = _as_bool(os.getenv("BLAST_RADIUS_LIVE_GENERATION"))
    session_ttl_minutes: int = int(os.getenv("BLAST_RADIUS_SESSION_TTL_MINUTES", "180"))
    daily_llm_budget: int = int(os.getenv("BLAST_RADIUS_DAILY_LLM_BUDGET", "100"))
    session_create_limit_per_hour: int = int(
        os.getenv("BLAST_RADIUS_SESSION_CREATE_LIMIT_PER_HOUR", "12")
    )
    round_request_limit_per_minute: int = int(
        os.getenv("BLAST_RADIUS_ROUND_REQUEST_LIMIT_PER_MINUTE", "30")
    )
    session_round_request_cap: int = int(
        os.getenv("BLAST_RADIUS_SESSION_ROUND_REQUEST_CAP", "30")
    )
    generator_model: str = "gpt-5.6-luna"
    adaptation_model: str = "gpt-5.6-terra"
    critic_model: str = "gpt-5.6-sol"

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"


settings = Settings()
