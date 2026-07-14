# Blast Radius

**Blast Radius is a browser game that teaches developers to operate AI coding agents
without rubber-stamping dangerous actions.** Inspect a proposed command, dependency,
tool manifest, diff, retrieved instruction, or marketplace skill; choose **approve**,
**sandbox**, or **reject**; then explain the tell. The verdict grades the decision and the
reasoning separately and always shows concrete evidence receipts.

The hosted application is designed for the OpenAI Build Week 2026 Developer Tools track.
It never executes scenario content.

## Why it is different

Most security games ask you to attack a system. Blast Radius trains the increasingly
important defender/operator reflex: deciding what an AI coding agent should be allowed to
do. Its core is a verification loop, not a quiz answer key:

```text
verified template -> bounded variation -> correctness gate -> player decision
                  -> immutable ground truth -> reasoning grade -> receipts
```

- 18 curated, receipt-backed scenarios across six threat families.
- Mandatory pre-display gate with a tested rejection path.
- Decision, reasoning, and sandbox quality scored independently.
- Five-question pre/post test and a session-local competency map.
- Deterministic judge mode that remains playable without an OpenAI API key.
- Optional GPT-5.6 live variations with automatic fallback to the verified bank.

## Run it locally

### Requirements

- Python 3.11 or newer
- A modern desktop or mobile browser
- Optional: an OpenAI API key with GPT-5.6 access for live variation mode

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn blast_radius.main:app --reload
```

macOS or Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
python -m uvicorn blast_radius.main:app --reload
```

Open <http://127.0.0.1:8000>. The verified run works immediately. To enable live mode,
set these values in `.env`:

```dotenv
OPENAI_API_KEY=your_server_side_key
BLAST_RADIUS_LIVE_GENERATION=true
```

The API key is read only by the server. It is never included in browser responses or logs.

## Test it

```powershell
.\.venv\Scripts\python -m pytest
```

The suite covers model validation, all curated scenarios, the correctness gate, grounded
grading, sandbox under/over-scoping, prompt injection in player reasoning, API leakage,
duplicate decisions, and the complete six-round demo session.

Useful endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Non-sensitive deployment health |
| `POST /api/sessions` | Start a `demo` or `live` session |
| `POST /api/sessions/{id}/pretest` | Submit the five baseline answers |
| `POST /api/sessions/{id}/rounds/next` | Retrieve a presentation-only scenario |
| `POST /api/sessions/{id}/decisions` | Grade an action, reasoning, and sandbox policy |
| `POST /api/sessions/{id}/posttest` | Submit the repeated test |
| `GET /api/sessions/{id}/results` | Retrieve the mastery result |
| `GET /api/docs` | Interactive API reference |

## Architecture and safety model

FastAPI serves the interface and API from one Python process. Pydantic owns every trust
boundary. SQLite stores opaque session state with an expiration time; there are no user
accounts or personal profiles.

Scenario ground truth stays server-side. The browser receives only the ask and artifacts
until a decision is committed. The deterministic correctness gate verifies:

1. the scenario belongs to a known, cited template;
2. template and scenario families agree;
3. every tell has a matching keyword/evidence group;
4. at least one declared tell is visible in the presented artifacts;
5. sandbox answers include a safe policy; and
6. evidence identifiers and receipts are complete.

If live generation times out, returns malformed structured output, or fails the gate, the
server selects a compatible curated fallback. Scenario commands are strings only; there is
no execution path in the application.

### GPT-5.6 roles

All model IDs live in `blast_radius/config.py`:

- `gpt-5.6-luna`: bounded scenario generation.
- `gpt-5.6-terra`: reserved for adaptive blind-spot targeting.
- `gpt-5.6-sol`: critic/gate configuration for the live verification path.

The current build uses the Responses API with Structured Outputs for optional generation.
Immutable curated evidence remains the grading authority, so an LLM cannot rewrite the
correct answer. The default demo does not spend API tokens.

## Supported platforms and judge testing

- Browsers: current Chrome, Edge, Firefox, and Safari; responsive down to mobile widths.
- Self-hosting: Windows, macOS, and Linux with Python 3.11+.
- Judge path: start the application and click **Start verified run**. It requires no login,
  API key, background worker, Node build, Docker image, or live generation.

Production deployment files for an Ubuntu VPS are in `deploy/`. Install into
`/opt/blast-radius`, configure the environment, enable the systemd unit, and use the Caddy
snippet for HTTPS. Keep the instance free and unrestricted through August 5, 2026, the end
of the official judging period.

## Built with Codex

This repository was implemented with Codex beginning July 14, 2026. The collaboration
artifacts are part of the submission evidence:

- The original plan and research package is preserved in the numbered Markdown files.
- `AGENTS.md` encodes the non-negotiable trust and security boundaries.
- `.agents/skills/verify-scenario/SKILL.md` packages the bank-verification workflow.
- Tests were written with the engine and API, including an adversarial scenario designed
  to prove that player prompt injection cannot alter immutable ground truth.
- The primary Codex `/feedback` session ID must be added here only after it is generated:
  **`PENDING — do not replace with an invented value`**.

No productivity, learning-delta, latency, or accuracy number is claimed here unless it was
measured from the running product.

## Prior work and exclusions

The application code in this repository is new work for the July 13–21, 2026 submission
period. The planning archive was produced before implementation and was imported as
historical/source material.

MaRa SIFT is prior, external work and is **not integrated into this submission build**.
The forensic-triage round from the original concept is deferred; no MaRa code, output, or
capability is copied or claimed. The six implemented families are dangerous commands,
poisoned dependencies, over-scoped tools, malicious diffs, poisoned context, and the
fictional skill marketplace.

## Submission checklist

- [ ] Hosted URL tested from a logged-out browser
- [ ] Public YouTube demo is under three minutes and has audio
- [ ] Video shows both Codex collaboration and GPT-5.6 usage
- [ ] `/feedback` session ID replaces the truthful placeholder above
- [ ] Repository is public and the MIT license is visible
- [ ] Fresh-machine setup instructions have been rehearsed
- [ ] Demo remains available through August 5, 2026

## License

MIT — see [LICENSE](LICENSE).

