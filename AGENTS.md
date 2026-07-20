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

- Optional presentation reskinning: `gpt-5.6-luna`; it may only rewrite presentation fields
  anchored to a curated scenario. Identity, truth, policy, and receipts stay immutable.
- Generated-presentation gate: `gpt-5.6-sol`, max reasoning effort.
- Verified-scenario reasoning critic: `gpt-5.6-sol`, medium reasoning effort.
- Generated presentations use deterministic tell-coverage grading and never enter the
  reasoning-critic prompt.
- The deterministic bank must remain fully usable without an API key.

## Commands

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m uvicorn blast_radius.main:app --reload
```

Windows:

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
- No email/password accounts, multiplayer, command execution, or storage of reasoning text in
  long-lived profiles. Three narrow, deliberate persistence features are part of the product:
  - **Browser-local history.** Learner progress lives only in a single versioned
    `localStorage` key, written and read exclusively by client-side code, and is never
    sent to or stored by the server — the ephemeral session row and its TTL remain the
    only server state. The UI always labels it "stored only in this browser" with a
    one-click clear, and the app stays fully functional when storage is unavailable. The
    random client key a browser may send when starting a daily drill is used transiently
    for deterministic scenario selection and is never persisted or logged. The browser's
    recently-seen scenario ids are treated the same way: they ride along as a transient
    `exclude` hint so repeat playthroughs rotate off just-seen scenarios, and are used only
    for selection — never persisted or logged server-side.
  - **The team board.** A session MAY carry an optional, self-chosen operator handle (max
    40 chars, no emails, no auth, no password, never required to play). Finished sessions
    write a scores-only summary row (handle, mode, test scores, delta, rounds, competency
    aggregates) that outlives the session TTL so the developer-role team board can
    aggregate them. Reasoning text, answers, IPs, and any other personal data are never
    persisted in summaries. Handles are display labels, not identities: they are not
    verified, not unique, and grant no access.
  - **Pseudonymous learner profiles and leaderboard.** A signed `br_uid` browser cookie maps to
    score, level, nickname, pet configuration, and aggregate session counts. A high-entropy
    recovery token may adopt that profile in another browser. Profiles never collect an email,
    password, reasoning text, raw answers, or IP address; the public leaderboard exposes only
    nickname, score, level, rank, and whether the row belongs to the current browser.
- The `/team` and `/author` pages are developer-role only and read-only with respect to the
  scenario bank: authored drafts are validated against the production gate and downloaded
  client-side; they enter the repo exclusively via PR + CI.
- The `/api/check` inspector and the CLI are deterministic keyword screens — they never run a
  model and never claim an artifact is safe. Do not add wording that implies otherwise.

## Submission evidence and copy

- The primary Codex build task is `/feedback` Session ID
  `019f606c-081a-7911-ba7b-114168f91dd1`; keep concrete Codex contributions in the README.
- The visible `494a258` merge records parallel workstreams with no history loss. Describe it
  plainly; do not imply the project had a single writer or hide the reconciliation.
- Prefer prove, verify, receipts, evidence, trust, accountability, “it caught its own mistake,”
  and hours saved. Avoid fear-first framing and unsupported metrics. If learning impact has not
  been measured with a consented named tester, write “Not yet measured.”
