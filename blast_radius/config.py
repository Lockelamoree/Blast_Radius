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


def parse_access_codes(raw: str) -> dict[str, str]:
    """Parse ``"judge:CODE,developer:CODE2"`` (or a bare ``"CODE"``) into a
    ``{code: label}`` map. Blank entries are ignored; a missing label becomes
    ``"guest"``. Codes are matched exactly, so keep them long and random."""
    codes: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        label, separator, code = entry.partition(":")
        if not separator:
            label, code = "guest", entry
        code = code.strip()
        label = label.strip() or "guest"
        if code:
            codes[code] = label
    return codes


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
    check_limit_per_minute: int = int(
        os.getenv("BLAST_RADIUS_CHECK_LIMIT_PER_MINUTE", "20")
    )
    gate_verify_limit_per_minute: int = int(
        os.getenv("BLAST_RADIUS_GATE_VERIFY_LIMIT_PER_MINUTE", "10")
    )
    team_summary_limit_per_minute: int = int(
        os.getenv("BLAST_RADIUS_TEAM_SUMMARY_LIMIT_PER_MINUTE", "30")
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
    # Access gate: when both a secret and at least one code are configured, every
    # route except /healthz, /access, /logout and /static is gated behind a
    # signed cookie. Absent config = open (keeps local dev and tests ungated).
    access_codes: str = os.getenv("BLAST_RADIUS_ACCESS_CODES", "")
    auth_secret: str = os.getenv("BLAST_RADIUS_AUTH_SECRET", "")
    auth_cookie_secure: bool = _as_bool(
        os.getenv("BLAST_RADIUS_AUTH_COOKIE_SECURE"), True
    )
    auth_cookie_ttl_days: int = int(
        os.getenv("BLAST_RADIUS_AUTH_COOKIE_TTL_DAYS", "30")
    )

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def access_code_map(self) -> dict[str, str]:
        return parse_access_codes(self.access_codes)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_secret) and bool(self.access_code_map)


settings = Settings()
