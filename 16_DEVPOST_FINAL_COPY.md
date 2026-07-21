# Blast Radius — final Devpost copy

> Paste-ready technical copy as of 2026-07-20, checked against live `/healthz`
> (revision `0e58d23`, 20 scenarios, `reasoning_grading: "live"`, critic `gpt-5.6-sol`).
> Gallery captures and the public demo video are in place.

## Project name

**Blast Radius**

## Tagline

**Size the risk. Verify the evidence. Then approve your AI coding agent.**

## Elevator pitch

Blast Radius turns the hardest part of supervising a coding agent into a playable reflex.
Its **20 receipt-linked scenarios** and **436-test verification suite** teach developers to
approve, sandbox, or reject proposed commands, dependencies, tool manifests, diffs, retrieved
instructions, and marketplace skills—and to prove the call with evidence.

Every scenario passes a deterministic gate before display. After each decision, the player sees
the exact action score, tell coverage, sandbox scope, and direct receipts. On verified rounds,
GPT-5.6 Sol can match only immutable allowlisted tells and ask a Socratic follow-up; it cannot
change the correct action, safe policy, or evidence. If a model call fails, the deterministic
path still completes the round.

Hosted demo: **https://blastradius.max-gutowski.de/**

Judges: the demo is in private preview. Put the supplied judge access code in Devpost's
**Testing access / credentials** field so the project can be tested without rebuilding.

## Inspiration

Developers increasingly supervise agents that ask permission to act. The valuable skill is not
memorizing attack names; it is deciding which proposed action deserves trust, how narrowly to
scope it, and what evidence proves that choice. Blast Radius makes that operator judgment
repeatable, inspectable, and easier to practice.

## What it does

The main six-round run starts with a shuffled five-question baseline. Each round presents an
inert agent artifact. The player chooses **approve / sandbox / reject**, writes one sentence
naming the tell, and—when sandboxing—sets readable paths, writable paths, network hosts, and
capabilities. The remaining verified deck adapts toward the learner's weakest competency without
changing any already-shown round. A distinct shuffled post-test then reports measured competency
change.

The same verification engine also powers:

- a primary **60-second verified incident** with no signup or assessment, while the full run keeps
  the existing pre/post measurement;
- a visible “it caught its own mistake” demo that plants two defects and shows both gate reasons;
- `/screen`, where a developer can paste a real command, diff, or sandbox policy for a
  deterministic, offline, model-free red-flag screen, inspect fixes, and download its JSON receipt;
- an offline CLI, MCP server, GitHub Action, Codex plugin, and Codex `PreToolUse` supervisor hook;
- a daily one-round drill, coached retry, local practice history, exportable guardrails, and
  offline detection/model evaluation;
- pseudonymous learner profiles with optional nickname, recoverable token, a draggable and
  keyboard-movable Blastling whose position stays device-local, score/level progression, and a
  scores-only public leaderboard;
- developer-only team and scenario-authoring views.

The product never executes the commands or code it shows.

## How I built it

Codex implemented the application as a Python FastAPI service with Pydantic, SQLite, Jinja,
vanilla JavaScript, and CSS. Repository and nested `AGENTS.md` files lock the engine, privacy,
accessibility, and browser invariants. A custom `verify-scenario` Codex skill calls the real
production correctness gate, and CI runs Ruff, the automated suite, the 20-scenario verifier,
wheel construction, and packaged-resource checks.

The architecture is a simple loop with receipts:

1. Select a server-owned verified scenario.
2. Optionally let GPT-5.6 Luna reskin presentation fields only.
3. Run the deterministic gate and a separate Sol consistency review.
4. Let the operator decide.
5. Grade against immutable truth and return direct evidence.

The product entry points are deliberately simple: **Learn** the six families, **Screen** a real
artifact, or **Integrate** the deterministic gate through the CLI, MCP, GitHub Action, Codex hook,
or a `.blastradius.toml` team policy. Each grade includes a SHA-256 fingerprint of the public
scenario presentation and the real deterministic gate result; grade, screen, and learning receipts
are downloadable without hidden ground-truth keys.

The browser never receives answer keys before grading. Ground truth, safe policies, and receipt
sources stay server-side. Per-session locks serialize duplicate mutations. Provider attempts
have session and daily budgets, Responses API calls use strict Structured Outputs and
`store: false`, and every failure keeps the deterministic fallback available.

## Model use and measured baseline

GPT-5.6 Sol is a bounded reasoning critic for verified rounds and a secondary consistency review
for generated presentations. GPT-5.6 Luna may rewrite presentation text only after a verified
anchor is selected; it cannot author truth or evidence.

The committed model-player baseline runs Sol through the same 20 scenarios and grades it with the
same deterministic engine as a person. It records **75% action accuracy** and **92% average tell
coverage**. Its five wrong calls lean toward **over-approval**: 3 over-approvals and 2
over-restrictions. The scorecard is committed at
`blast_radius/data/model_eval_baseline.json` and served read-only at `GET /api/eval/model`.
These are corpus results, not a real-world safety claim.

## Verification proof

The committed live-grade proof was captured at revision
`9b5e92efbd7d2d1ca023f0ead2b545c50cddc452`, with 20 scenarios, live generation available,
live reasoning grading, and critic model `gpt-5.6-sol`. That historical revision remains in the
receipt rather than being rewritten. Before final screenshots, run the submission preflight
against `/healthz` to prove that the newly deployed revision matches the pushed commit.

A fresh hosted round produced provider response
`resp_024208198fc0ff3c016a5cbcdbd3708192887a3ae615e727a1`. The committed receipt embeds that
response ID at the top level and inside `critic_proof`, plus the matching health snapshot,
revision, hashed session correlation, raw application grade, and receipt SHA-256:

`evidence/live_grade_resp_024208198fc0ff3c016a5cbcdbd3708192887a3ae615e727a1.json`

## Screens

The gallery uses stable paths so the three live captures can be replaced without editing this
copy. The current images are annotated staging assets; replace them with final live screenshots
before submission.

![Decision Card: review an agent proposal, choose approve/sandbox/reject, and name the evidence tell](https://raw.githubusercontent.com/Lockelamoree/Blast_Radius/main/assets/screen_decision.png)

*Decision Card — the operator makes the call and names the evidence tell.*

![Verdict Stamp: graded reasoning with direct receipts and the visible gate result](https://raw.githubusercontent.com/Lockelamoree/Blast_Radius/main/assets/screen_verdict.png)

*Verdict Stamp — scored reasoning, verified receipts, and the gate result.*

![The landing: the operator's-seat pitch, the proof strip, and the three ways to play](https://raw.githubusercontent.com/Lockelamoree/Blast_Radius/main/assets/screen_results.png)

*The landing — the operator's seat, the proof strip (20 scenarios · 6 families · 0 commands executed · 100% receipt-backed), and the three ways to play.*

## Potential impact

Blast Radius is designed for developers who already use coding agents but need a faster,
evidence-first approval habit. It can be used as a short training run, a daily drill, a CI gate
for authored scenarios, or an advisory screen beside a real agent workflow. The value is a
repeatable operator reflex and an inspectable record of why a call was made.

Every session brackets play with a distinct pre-test and post-test and reports the per-competency
delta on screen, so a player sees their own movement immediately — the measurement loop is built in
and inspectable.

## What I learned

Verification becomes convincing when the user can inspect the boundary. A model can help match
reasoning and vary presentation, but immutable inputs, bounded outputs, deterministic fallback,
and direct receipts are what make the agent experience trustworthy. The strongest demo moment is
simple: **it caught its own mistake before the user saw it.**

## Built with Codex

Primary Codex `/feedback` Session ID:
**019f606c-081a-7911-ba7b-114168f91dd1**.

Codex created the application spine, correctness gate, data models, API/session orchestration,
browser experience, custom verifier skill, integrations, adversarial tests, deployment checks,
and proof-capture harness. The visible `494a258` merge reconciles parallel Codex workstreams after
the integrity-tab change was already present in the larger gate/accounts branch; it records both
parents with no history loss, and the merged tree passed the same verification loop.

## Installation and supported platforms

Hosted use needs a current desktop or mobile browser. Self-hosting supports Windows, macOS, and
Linux with Python 3.11 or newer. Production deployment targets Ubuntu 24.04 LTS.

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

Open `http://127.0.0.1:8000`. The deterministic run works without an API key.

## Links

- Hosted demo: **https://blastradius.max-gutowski.de/**
- Walkthrough &amp; proof (annotated screenshots + the live gate-catch JSON): **https://lockelamoree.github.io/Blast_Radius/**
- Source: **https://github.com/Lockelamoree/Blast_Radius**
- Public video: **https://www.youtube.com/watch?v=ybRj2Z5t8oU**
- License: **MIT**

## Human submission checklist

- Paste this copy into the Developer Tools track submission.
- Put the supplied judge access code in Devpost's testing-access field.
- Replace the three gallery PNGs with live captures.
- Add the public video URL after recording.
- Confirm the Devpost page is submitted and the hosted demo remains available through August 5.
