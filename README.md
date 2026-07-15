# Blast Radius

**Blast Radius is a browser game that teaches developers to operate AI coding agents
without rubber-stamping dangerous actions.** Inspect a proposed command, dependency, tool
manifest, diff, retrieved instruction, or marketplace skill; choose **approve**,
**sandbox**, or **reject**; then explain the tell. The verdict grades the decision and
reasoning separately and shows concrete evidence receipts.

The application is designed for the OpenAI Build Week 2026 Developer Tools track. It never
executes scenario content.

## Why it is different

Most security games ask you to attack a system. Blast Radius trains the defender/operator
reflex: deciding what an AI coding agent should be allowed to do. Its core is a verification
loop, not a quiz answer key:

```text
verified template -> bounded variation -> correctness gate -> player decision
                  -> immutable ground truth -> reasoning grade -> receipts
```

- 18 curated, receipt-backed scenarios across six threat families.
- Mandatory pre-display gate with a tested rejection path and visible self-catch demo.
- Decision, reasoning, and sandbox quality scored independently.
- Five-question pre/post test, session-local competency map, and shareable measured result.
- Deterministic judge mode that remains playable without an OpenAI API key.
- GPT-5.6 reasoning critique whenever a key is present; live generation remains opt-in.

## Try it

Hosted demo: **TODO — add the public HTTPS URL only after the VPS/domain deployment is
complete and verified from a logged-out browser.**

### Requirements

- Python 3.11 or newer
- A current Chrome, Edge, Firefox, or Safari browser
- Optional: a server-side OpenAI API key with GPT-5.6 access

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

Open <http://127.0.0.1:8000>. The verified run works immediately. Setting only
`OPENAI_API_KEY` enables GPT-5.6 reasoning critique while keeping every scenario curated.
Fresh scenario generation is a separate opt-in:

```dotenv
OPENAI_API_KEY=your_server_side_key
BLAST_RADIUS_LIVE_GENERATION=true
BLAST_RADIUS_DAILY_LLM_BUDGET=500
```

The key stays server-side and is never included in browser responses or model-payload logs.
Once the UTC daily call budget is exhausted, grading degrades transparently to the
deterministic path.

## Test it

```powershell
.\.venv\Scripts\python -m pytest
```

The suite covers model validation, every curated scenario, the correctness gate, grounded
grading, model failure and budget fallback, sandbox scoping, adversarial player text, API
leakage, rate limits, duplicate decisions, and the complete six-round demo session.

Useful endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Non-sensitive deployment health |
| `GET /api/demo/gate-catch` | Show the gate rejecting a planted hallucination |
| `POST /api/sessions` | Start a `demo` or `live` session |
| `POST /api/sessions/{id}/pretest` | Submit the five baseline answers |
| `POST /api/sessions/{id}/rounds/next` | Retrieve a presentation-only scenario |
| `POST /api/sessions/{id}/decisions` | Grade an action, reasoning, and sandbox policy |
| `POST /api/sessions/{id}/posttest` | Submit the repeated test |
| `GET /api/sessions/{id}/results` | Retrieve the mastery result |
| `GET /api/docs` | Interactive API reference |

## Architecture and safety model

FastAPI serves the interface and API from one Python process. Pydantic owns every trust
boundary. SQLite stores opaque session state, expiration data, and the atomic UTC daily
model-call budget; there are no accounts or personal profiles.

Scenario ground truth stays server-side. The browser receives only the ask and artifacts
until a decision is committed. The deterministic correctness gate verifies template
membership, family consistency, tell/evidence coverage, visible artifact support, sandbox
policy safety, and receipt completeness. If generation times out, returns malformed output,
or fails either gate, a compatible curated fallback is selected. Commands remain inert
strings with no execution path.

```text
Browser
  -> FastAPI session/API boundary
      -> deterministic bank + correctness gate
      -> GPT-5.6 augmentation (optional, budgeted)
      -> immutable grade + receipts
      -> SQLite session and daily-budget store
```

### GPT-5.6 roles

All model IDs live in `blast_radius/config.py`:

- `gpt-5.6-luna`: bounded scenario generation at medium effort.
- `gpt-5.6-terra`: adaptive blind-spot targeting at low effort.
- `gpt-5.6-sol`: semantic reasoning critique at medium effort and generated-scenario critique
  at max effort.

The build uses the Responses API with Structured Outputs. Sol may add only recognized tells
from the immutable allowlist and write the follow-up. It cannot rewrite the correct action,
evidence, receipts, or sandbox policy. Without a key—or after the daily budget is
exhausted—the same flow uses deterministic grading.

## Deployment and supported platforms

- Browsers: current Chrome, Edge, Firefox, and Safari; responsive to mobile widths.
- Self-hosting: Windows, macOS, and Linux with Python 3.11+.
- Judge path: **Start verified run** requires no login, API key, Node, Docker, or rebuild.

Production files are in `deploy/`. With DNS already pointed at an Ubuntu VPS:

```bash
sudo OPENAI_API_KEY='spend-capped-key' bash deploy/deploy.sh your-domain.example
```

The script installs the Python service and Caddy, enables HTTPS, and checks `/healthz`.

## Built with Codex

This repository was implemented with Codex beginning July 14, 2026. Evidence in the public
tree is limited to artifacts a judge can inspect:

- `AGENTS.md` and nested guidance encode the non-negotiable engine and UI boundaries.
- `.agents/skills/verify-scenario/SKILL.md` invokes the real bank-verification workflow.
- Tests include adversarial player text proving prompt injection cannot alter ground truth.
- The dated commit history distinguishes the implementation work.
- Codex `/feedback` Session ID: **TODO — add the real ID from the primary build thread; do
  not invent one.**

Measured developer pre/post result: **TODO — add one real named run; no result has been
claimed yet.** No productivity, learning-delta, latency, or accuracy number is claimed
without a captured measurement.

## Prior work and exclusions

The application code in this repository was implemented during the July 13–21, 2026
submission period; the dated commit history is the evidence for that work.

MaRa SIFT is prior, external work and is **not integrated into this submission build**. The
forensic-triage round is deferred; no MaRa code, output, or capability is copied or claimed.
The six implemented families are dangerous commands, poisoned dependencies, over-scoped
tools, malicious diffs, poisoned context, and the fictional skill marketplace.

## Submission checklist

- [ ] Hosted URL tested from a logged-out browser
- [ ] Public YouTube demo is under three minutes and has audio
- [ ] Video shows both Codex collaboration and GPT-5.6 usage
- [ ] Real `/feedback` Session ID replaces the truthful TODO
- [ ] One named developer’s measured pre/post result replaces the truthful TODO
- [ ] Fresh-machine setup instructions have been rehearsed
- [ ] Demo remains available through August 5, 2026

## License

MIT — see [LICENSE](LICENSE).
