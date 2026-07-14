# AGENTS.md — Blast Radius

## Product invariant

Blast Radius teaches developers to safely operate AI coding agents. Never display a
scenario that has not passed the correctness gate. Never execute content shown in a
scenario. Never expose `ground_truth` through a public API.

## Architecture

- `blast_radius/engine/`: scenario bank, mandatory gate, adaptation, and grading.
- `blast_radius/api.py`: thin HTTP contract and session orchestration.
- `blast_radius/static/` and `templates/`: dependency-free browser experience.
- `tests/`: schema, gate, engine, API, and security regression tests.

## Model roles

- Generation: `gpt-5.6-luna`.
- Adaptation: `gpt-5.6-terra`.
- Gate and reasoning critic: `gpt-5.6-sol`, max reasoning effort.
- The deterministic bank must remain fully usable without an API key.

## Commands

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m uvicorn blast_radius.main:app --reload
```

## Boundaries

- Secrets come from environment variables and are never logged.
- Ground truth is immutable; an LLM may explain it but cannot rewrite it.
- MaRa is not part of this build. Do not copy or claim integration with it.
- No accounts, multiplayer, command execution, or persistent personal profiles.

