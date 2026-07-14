# Blast Radius — Codex Playbook

> **This is the highest-leverage document.** Judging ties break on *Technological Implementation* — how skillfully you used Codex — so your Codex session, `AGENTS.md`, custom Skill, and README "Built with Codex" chapter are **judged artifacts**. This playbook makes them excellent. Assume a judge reads the transcript.

## Golden rules

1. **One primary Codex thread** for the majority of core functionality. This is the thread whose **`/feedback` Session ID** you submit. Keep it coherent: `/plan` first, work in tight loops, `/compact` when it drifts.
2. **`/plan` before building each work package.** Let Codex propose the approach; refine; then execute. The plan artifacts are evidence of skillful use.
3. **`/review` before every merge**, and once on the whole codebase before submission. Blast Radius *teaches reviewing agent output* — dogfooding `/review` is thematically perfect and worth saying out loud in the README + video.
4. **Tests alongside code**, not after. The engine (generator schema, correctness gate, grader) must have tests.
5. **Every prompt states: goal, context, constraints, completion criteria.** No vibe prompts.
6. **Screen-record everything** (you set this up Day 0). The video needs footage of the `/plan`, the Skill wrapping tools, and a real `/review` catch.
7. **Verify GPT-5.6 API specifics against live docs on Day 1** before wiring the engine (model IDs, Structured Outputs, reasoning-effort, prompt caching). The spec's names are second-hand.

---

## AGENTS.md (paste into repo root, edit paths as Codex scaffolds)

```markdown
# AGENTS.md — Blast Radius

## What this project is
Blast Radius is a browser game that teaches developers to safely operate AI coding
agents. Players make APPROVE / SANDBOX / REJECT calls on proposed agent actions; a
GPT-5.6 critic grades their *reasoning* against verified ground truth and shows receipts.
The engine is a self-critiquing loop: generate -> correctness-gate -> adapt -> grade.

## Non-negotiable domain rules
- NEVER display a scenario that has not passed the critic correctness gate. A scenario
  that teaches a false or unverifiable security lesson is a critical defect.
- The generator only produces BOUNDED VARIATIONS on the verified template spine in
  `engine/spine/`. It must never free-invent a vulnerability class.
- Every graded verdict must carry at least one RECEIPT: a concrete, checkable claim
  (e.g. "package absent from PyPI", "manifest scope contradicts egress"). No receipt,
  no verdict.
- Ground truth lives in the Scenario object; grading compares against it, never vibes.
- The demo path runs off the curated fallback bank in `engine/bank/`, not live generation.

## Architecture (keep it a "for-loop with receipts", not scaffolding)
- `engine/`  — generator, adversary, critic-grader, spine, fallback bank. Pure, testable.
- `server/`  — thin API that calls GPT-5.6 (key from env, never committed).
- `ui/`      — single-page browser app. No build step required to *run* the hosted demo.

## Model usage
- Bulk generation: cheap GPT-5.6 tier.
- Critic correctness gate + grading: flagship tier, max reasoning effort.
- Prompt-cache the static spine + rubric preamble.
- All model IDs and feature flags are defined in `engine/models.*` — change them in ONE place.

## Conventions
- Language/stack: <Codex fills in on Day 1 — pick one boring, fast stack and stick to it>.
- Tests live next to code; run `<test command>` before every commit.
- Run `/review` before merging any branch.
- Secrets via env only. `.env` is git-ignored. Never log a key or a full API response with a key.

## What NOT to do
- No multiplayer, accounts, XP economy, art assets, or offense-only CTF mode (see spec cut list).
- Do not copy MaRa SIFT source into this repo. It is an EXTERNAL MCP dependency, documented
  in the README's "Prior work vs. new work" section. This repo is 100% new work.
```

**Nested AGENTS.md** — add short ones in `ui/` ("keep it a fast single-page app, dark developer-terminal aesthetic, one tasteful moment of wit, no framework churn") and `engine/` ("pure functions, every public fn tested, the gate is mandatory and has a test that feeds it a known-bad scenario and asserts rejection").

---

## Custom Codex Skill — the "verify-scenario" gate (your signature artifact)

Package the correctness gate as a reusable Codex Skill. Almost no competitor will have a self-authored Skill — it's the clearest possible proof of Codex depth, and it *is* the self-critiquing loop the judges reward. Create `.agents/skills/verify-scenario/SKILL.md` (confirm the exact skills path/format against current Codex docs on Day 1):

```markdown
# SKILL: verify-scenario

## Purpose
Given a generated Blast Radius scenario, verify it is correct and safe to show a learner,
and return a structured verdict. Use this as the mandatory gate before any scenario is
displayed, and reuse it to bulk-verify the fallback bank.

## When to use
- Before displaying any generated scenario.
- When adding or editing a template in engine/spine/.
- When curating the fallback bank.

## Steps
1. Parse the Scenario object (presentation + ground_truth + template_ref).
2. Check internal consistency: does ground_truth.correct_action actually follow from the
   presented artifacts? Does each claimed tell have a real, checkable receipt?
3. Cross-check the security claim against the cited spine template. Reject anything that
   asserts a vulnerability or fix not grounded in the spine.
4. Confirm the scenario teaches a TRUE lesson (no hallucinated exploit, no wrong fix).
5. Return { pass: bool, reasons[], repaired_scenario? }.

## Output contract
Structured JSON matching engine/schemas/gate_verdict. `pass:false` => scenario is discarded
and the engine falls back to the curated bank.
```

Use this Skill **on camera** to bulk-verify the fallback bank — that's your "wrapped 20 scenarios in minutes" video beat.

---

## MCP inception (a story only you can tell)

Connect the **MaRa SIFT MCP server** to Codex *during development*, and also use it as the runtime oracle for the forensic-triage round.

- **During the build:** with MaRa SIFT connected as an MCP server in Codex, Codex can call real forensic tools to generate/verify the forensic round's ground truth against genuine evidence — "the agent that built the game used real forensic tools to make the game honest." Narrate this in the README + video.
- **At runtime:** the forensic-triage round's ground truth comes from real MaRa SIFT tool output (run offline into fixtures, or called live from `server/`), not invented artifacts.
- MaRa SIFT lives at `~/Desktop/MaRa` (`server.py` is its MCP entrypoint). It is **pre-existing** — reference it as an external dependency, document it in "Prior work vs. new work," and never copy its code into this repo.

---

## Parallel Codex agents (verify the verifier)

- Run the **UI build as a parallel worktree agent** while the primary thread builds the engine (Day 16 in the schedule).
- Run an **adversarial agent** whose job is to *make the grader accept a wrong answer* or *sneak a bad scenario past the gate*. Every hole it finds becomes a test. This literally shows you verified your own verification layer — catnip for Sottiaux/Korevec. Cite it in the README.

---

## Per-work-package Codex prompts (paste-ready)

Run these roughly in schedule order. Always let Codex `/plan` first on the bigger ones.

**WP1 — Repo + data model (Jul 13).**
> Goal: scaffold the Blast Radius repo and commit the core data model. Context: read `01_PRODUCT_SPEC.md` §8 in this folder. Constraints: pick one boring, fast stack (state your choice and why); set up tests, linting, and a `.env`-based secret pattern; create `engine/`, `server/`, `ui/` with the nested AGENTS.md files. Completion: `Scenario`, `PlayerDecision`, `GradeResult`, `LearnerProgress` types exist with tests that construct and validate them; CI/test command documented in AGENTS.md.

**WP2 — Verified spine + fallback bank + gate (Jul 14, THE priority).**
> Goal: build the verified scenario template spine, a curated fallback bank of ~15–20 scenarios, and the critic correctness gate. Context: `01_PRODUCT_SPEC.md` §3, §5, §7; sources in `research/`. Constraints: each template must cite a real pattern (OWASP LLM Top 10, CVE-2025-53773 slopsquatting/RCE patterns, MCP supply-chain); the gate is a mandatory pre-display check implemented via the `verify-scenario` Skill; write a test that feeds a deliberately-wrong scenario and asserts the gate rejects it. Completion: gate blocks known-bad scenarios in tests; the fallback bank passes the gate; every bank scenario has tells + receipts + citation.

**WP3 — GPT-5.6 engine wiring (Jul 14–15).**
> Goal: wire the generator, adversary, and critic-grader to GPT-5.6. Context: `01_PRODUCT_SPEC.md` §5; verify model IDs/Structured-Outputs/reasoning-effort against live OpenAI docs FIRST and record them in `engine/models`. Constraints: generator uses Structured Outputs against the Scenario schema; critic uses the flagship tier at max reasoning effort; prompt-cache the static spine; all model config in one file; cheap tier for bulk gen. Completion: given a template + difficulty, the engine emits a gate-passing Scenario; given a PlayerDecision, it returns a GradeResult with receipts.

**WP4 — Core loop + adaptation + grading (Jul 15).**
> Goal: implement the five action-family rounds, the APPROVE/SANDBOX/REJECT flow with blast-radius config, one-line reasoning capture, reasoning-first grading, and adversary adaptation from the competency map. Completion: a full session runs headless in tests (pre-test → N rounds → post-test) producing a LearnerProgress with a delta.

**WP5 — Fold-in rounds (Jul 16, parallelizable).**
> Goal: add the skill-marketplace audit round (fictional marketplace; README+manifest+source+egress artifacts; INSTALL/SANDBOX/QUARANTINE) and the forensic-triage round backed by real MaRa SIFT output. Context: `01_PRODUCT_SPEC.md` §4 + MCP inception above. Completion: both rounds pass the gate and grade correctly; forensic ground truth traces to real tool output.

**WP6 — Browser UI (Jul 16, parallel worktree agent).**
> Goal: build the single-page UI per `01_PRODUCT_SPEC.md` §9: round view, timer, decision + blast-radius configurator, reasoning box, verdict/receipts reveal with a beat of animation, pre/post test screens, mastery/competency screen, one tasteful moment of wit. Constraints: dark developer-terminal aesthetic; fast; runs hosted with no build step; mobile-web friendly. Completion: the fixed demo path (§10) is clickable end-to-end off the fallback bank.

**WP7 — Hosting + Dev Tools requirements (Jul 17).**
> Goal: deploy a one-click, pre-loaded, judge-testable demo to the VPS with a spend-capped key, and write the install/setup instructions + supported platforms. Completion: a logged-out browser can play the demo with zero setup; README "Run it yourself" section reproduces a local run.

**WP8 — Docs + `/review` pass (Jul 18).**
> Goal: run `/review` on the whole codebase, fix findings, and write the README including the "Built with Codex" chapter and "Prior work vs. new work". Completion: `/review` clean; README complete (template below); dated commit history tells the build story.

---

## README "Built with Codex" chapter (template)

```markdown
## Built with Codex

Blast Radius was built in a single primary Codex thread between July 13–18, 2026.
Codex session: /feedback ID `<PASTE>`.

- **Planning:** every work package started with `/plan` (screenshots in `docs/`).
- **AGENTS.md:** repo-root + nested guides encode the domain rules Codex followed —
  most importantly "never display a scenario that fails the correctness gate."
- **Custom Skill:** `verify-scenario` (`.agents/skills/`) packages the critic gate; we used
  it to bulk-verify the fallback bank.
- **MCP inception:** the MaRa SIFT MCP server was connected to Codex during development so
  Codex could ground the forensic round in real tool output — the agent that built the game
  used real forensic tools to keep it honest.
- **Parallel agents:** the UI was built in a parallel worktree while the engine progressed;
  an adversarial agent tried to sneak wrong answers past the grader, and every hole it found
  became a test.
- **Review:** `/review` ran before every merge and once on the whole codebase — fitting, since
  the product itself teaches reviewing agent output.

### How GPT-5.6 powers the product
- **Generator** (cheap tier, Structured Outputs) — fresh, non-Googleable scenarios.
- **Adversary** (mid tier) — targets the player's blind spots.
- **Critic-Grader** (flagship, max reasoning effort) — correctness gate + reasoning-first grading with receipts.
- ~1M context holds the full spine; prompt caching keeps the static preamble cheap.

### Prior work vs. new work
This repository is 100% new work created during the submission period. It depends on the
**MaRa SIFT MCP server** (pre-existing, external, `github.com/<...>`) only as a runtime tool
provider for the forensic-triage round; none of its code is included here.
```
