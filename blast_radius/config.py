from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_revision(value: str | None) -> str:
    revision = (value or "").strip().lower()
    if revision in {"dev", "unknown"} or re.fullmatch(r"[0-9a-f]{7,64}", revision):
        return revision
    return "unknown"


@dataclass(frozen=True)
class Settings:
    base_dir: Path = Path(__file__).resolve().parent
    database_path: Path = Path(os.getenv("BLAST_RADIUS_DATABASE", "blast_radius.db"))
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    live_generation: bool = _as_bool(os.getenv("BLAST_RADIUS_LIVE_GENERATION"))
    enable_docs: bool = _as_bool(os.getenv("BLAST_RADIUS_ENABLE_DOCS"))
    session_ttl_minutes: int = int(os.getenv("BLAST_RADIUS_SESSION_TTL_MINUTES", "180"))
    daily_llm_budget: int = int(os.getenv("BLAST_RADIUS_DAILY_LLM_BUDGET", "500"))
    critic_timeout_seconds: float = float(
        os.getenv("BLAST_RADIUS_CRITIC_TIMEOUT_SECONDS", "8")
    )
    generation_timeout_seconds: float = float(
        os.getenv("BLAST_RADIUS_GENERATION_TIMEOUT_SECONDS", "15")
    )
    session_llm_call_cap: int = int(
        os.getenv("BLAST_RADIUS_SESSION_LLM_CALL_CAP", "12")
    )
    generated_rounds_per_session: int = int(
        os.getenv("BLAST_RADIUS_GENERATED_ROUNDS_PER_SESSION", "5")
    )
    generation_budget_reserve: int = int(
        os.getenv("BLAST_RADIUS_GENERATION_BUDGET_RESERVE", "60")
    )
    revision: str = _as_revision(os.getenv("BLAST_RADIUS_REVISION", "unknown"))
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
    critic_model: str = "gpt-5.6-sol"
    generator_max_output_tokens: int = int(
        os.getenv("BLAST_RADIUS_GENERATOR_MAX_OUTPUT_TOKENS", "2048")
    )
    gate_max_output_tokens: int = int(
        os.getenv("BLAST_RADIUS_GATE_MAX_OUTPUT_TOKENS", "4096")
    )
    reasoning_max_output_tokens: int = int(
        os.getenv("BLAST_RADIUS_REASONING_MAX_OUTPUT_TOKENS", "2048")
    )

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"


settings = Settings()
