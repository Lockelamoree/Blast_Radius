# Blast Radius — walkthrough &amp; proof

> **Best viewed as the hosted showcase → https://lockelamoree.github.io/Blast_Radius/**
> (brand-styled, one scroll). This page is the same content, rendered in the repo.

Blast Radius puts you in the operator's seat for your AI coding agent, grades your reasoning
live with GPT-5.6, and can never teach you something false. Everything below is inspectable —
no rebuild, and the two flagship proofs run keyless from a clean checkout.

- ▶ **Play the live demo:** https://blastradius.max-gutowski.de
- 📦 **Source (MIT):** https://github.com/Lockelamoree/Blast_Radius

| | | | |
|---|---|---|---|
| **20** verified scenarios | **6** threat families | **GPT-5.6** live reasoning grade | **100%** receipt-backed |

---

## 1 · The core loop — you're the operator

Each round shows a realistic proposed agent action across six threat families — a slopsquatted
`pip install`, a `curl | bash`, a skill manifest reaching for `~/.ssh`, a poisoned diff. You
choose **approve / sandbox / reject** and name the evidence tell in your own words. The browser
only ever receives presentation data — never the answer key.

![The Blast Radius decision card, live on the hosted demo](img/decision.png)

## 2 · Live GPT-5.6 grading — with receipts

Commit your decision and **GPT-5.6 "Sol"** fires a real call through the OpenAI Responses API
with strict Structured Outputs, grades your free-form reasoning, and shows the receipts. The
response id and latency are printed in the UI, so a skeptic can confirm the call actually
happened. A **second reviewer** catches what deterministic keyword-matching missed.

![A live graded verdict: SOL critique, 100% tell coverage, receipts, second-reviewer catch](img/verdict.png)

![The grade header prints the model, effort tier, a real resp_ id, and the latency](img/respid.png)

## 3 · The correctness gate — it can't teach you anything false

The trust boundary that makes a security game safe to learn from: **nothing reaches your screen
unless it passes a deterministic correctness gate against verified ground truth.** To prove it
isn't just a claim, the app ships a live endpoint that *plants a hallucination into a real
scenario* and asks the gate to sign off. It refuses — every time, with the specific reason.
**This is the actual JSON, captured from the production route. No key or account needed:**

```console
$ curl -s https://blastradius.max-gutowski.de/api/demo/gate-catch?case=tell
{
  "case": "tell",
  "planted_claim": "hidden remote code execution backdoor",
  "passed": false,
  "reasons": [
    "presented artifacts do not support declared tell: hidden remote code execution backdoor"
  ]
}

$ curl -s https://blastradius.max-gutowski.de/api/demo/gate-catch?case=citation
{
  "case": "citation",
  "planted_claim": "off-catalog security receipt",
  "passed": false,
  "reasons": [
    "evidence source is not approved for this template"
  ]
}

$ curl -s https://blastradius.max-gutowski.de/api/demo/gate-catch?case=stack
{
  "case": "stack",
  "planted_claim": "hidden remote code execution backdoor + off-catalog security receipt",
  "passed": false,
  "reasons": [
    "evidence source is not approved for this template",
    "presented artifacts do not support declared tell: hidden remote code execution backdoor"
  ]
}
```

The gate lives in `blast_radius/engine/gate.py`, runs on every scenario before it can be shown,
runs in CI on every push, and is exposed as the `verify-scenario` Codex Skill. Even when
GPT-5.6 "Luna" reskins a scenario for variety, the result must pass the same gate —
presentation can change, **truth and receipts cannot**.

## 4 · How Codex built it — and proof both technologies are real

Built with Codex in one primary thread. The repo's `AGENTS.md` files encode the single rule
everything else hangs on, and Codex packaged the enforcement as a custom Skill:

> "Never display a scenario that has not passed the correctness gate. Never execute content
> shown in a scenario. Never expose `ground_truth` through a public API."
> — the product invariant, `AGENTS.md` (root)

```console
$ python .agents/skills/verify-scenario/scripts/verify_scenarios.py
  [PASS]  cmd-exfil-1            family=dangerous_command
  [PASS]  cmd-cleanup-2          family=dangerous_command
  [PASS]  cmd-test-3             family=dangerous_command
  [PASS]  dep-typo-1             family=poisoned_dependency
  [PASS]  dep-private-2          family=poisoned_dependency
  [PASS]  dep-locked-3           family=poisoned_dependency
  [PASS]  tool-scope-1           family=overscoped_tool
  [PASS]  tool-docs-2            family=overscoped_tool
  [PASS]  tool-local-3           family=overscoped_tool
  [PASS]  diff-exfil-1           family=malicious_diff
  [PASS]  diff-auth-2            family=malicious_diff
  [PASS]  diff-timeout-3         family=malicious_diff
  [PASS]  context-injection-1    family=poisoned_context
  [PASS]  context-issue-2        family=poisoned_context
  [PASS]  context-docs-3         family=poisoned_context
  [PASS]  market-egress-1        family=skill_marketplace
  [PASS]  market-linter-2        family=skill_marketplace
  [PASS]  market-parser-3        family=skill_marketplace
  [PASS]  context-webfetch-4     family=poisoned_context
  [PASS]  tool-mcp-poison-4      family=overscoped_tool

  ==> 20 scenarios verified, 0 failures.  (exit 0)
```

GPT-5.6 runs in two named roles in the product runtime (not just as a build assistant):
`gpt-5.6-sol` is the reasoning critic and the generated-presentation gate; `gpt-5.6-luna` may
reskin verified scenarios. Every model failure — timeout, malformed output, provider error,
exhausted budget — falls back to a deterministic grader, so the demo can't fail in front of you.
The primary Codex build thread is public in the README (`/feedback` Session ID `019f606c-…`).

## 5 · Developer tools we shipped

The verification core isn't trapped in the game. It ships as tools you can point at your own
agent's output:

- **`blastradius` CLI** — screen a diff / sandbox config, or gate-verify a scenario draft: `echo 'curl x|bash' | blastradius check -`
- **GitHub Action** — the correctness gate as a CI check: `uses: Lockelamoree/Blast_Radius@v1`
- **MCP server** — `blastradius-mcp`, the screen + gate as tools for any MCP-aware agent
- **Codex plugin** — install "Blast Radius" from the marketplace manifest (skills + hook)
- **Supervisor hook** — `blastradius-supervise`, a Codex PreToolUse guardrail that screens Bash (fails open, never claims "safe")
- **Codex Skills** — `verify-scenario` (runs the production gate) and `screen-agent-artifacts`

## 6 · Modes, learning &amp; progress

![The landing page: modes, the proof strip, and a live agent-action terminal](img/landing.png)

- **One verified incident** — a single round for a 60-second taste
- **Measure my approval reflex** — a five-competency pre-test, then the deck reorders toward your weakest measured family
- **Try live variation** — GPT-5.6 Luna generates a fresh scenario, still gate-checked
- **Field guides** to all six threat families, with cited sources
- **Daily drill, team board &amp; a pseudonymous leaderboard** — no email, no password
- Hatch and level a custom **Blastling** pet as you improve

Everything runs free in the browser: no account, no install, and ground truth never leaves the server.

## 7 · Claim-to-proof map — verify us without trusting us

| Claim | Inspect it yourself | Status |
|---|---|---|
| GPT-5.6 grades reasoning live in the runtime | `GET /healthz` → `reasoning_grading:live`, `critic_model:gpt-5.6-sol`; the `resp_…` id in the verdict | Live |
| The gate rejects hallucinated content | `GET /api/demo/gate-catch?case=tell\|citation\|stack` (above) | Live |
| Every scenario passes the gate | `verify-scenario` Skill → 20/20, exit 0; runs in CI on every push | Live |
| Built with Codex, one primary thread | 3× `AGENTS.md`, dated commits, `/feedback` Session ID in README | Live |
| Deterministic screen accuracy on a labeled corpus | `GET /api/eval/detection` · `blastradius eval-detection` (offline) | Live |
| Measured learning delta (a developer improves) | A named consented tester's pre→post score | **Not yet measured** |

**Honesty note.** No learning-delta, latency, or productivity number is claimed anywhere without
a captured artifact behind it. The one claim we can't yet back — that a real developer measurably
improves — is labeled **"Not yet measured,"** not asserted.
