# Blast Radius — Judging Rubric (the brain)

> Canonical scoring rubric for the standing judge. Used by the judging workflow AND readable by Codex so it can self-check. Source of truth for what "excellent vs. weak" looks like for THIS project. Scores are 0–10 per criterion; the four criteria are **equally weighted**; **ties break on Technological Implementation first.** Be harsh — score against the *best* submissions in the track, not against zero.

## STAGE-ONE KILL GATE (pass/fail — checked first, every review)

If any of these fail, the project is **dead regardless of quality**. Fix before anything else.

- [ ] **Fits the theme** — a real, working project built for Build Week.
- [ ] **Uses Codex** — provable: primary session, `AGENTS.md`, dated commit history, `/feedback` Session ID.
- [ ] **Uses GPT-5.6** — *in the product runtime* (generator/adversary/critic), not just as a build assistant. Both technologies are required.
- [ ] **Judge-testable without rebuilding** — hosted demo URL, one-click, pre-loaded (Dev Tools requirement); credentials in testing notes if gated.
- [ ] **Submission artifacts present** — public repo + OSI license, README with a Codex-collaboration chapter, `<3:00` public YouTube video showing *both* technologies, install/setup instructions + supported platforms (Dev Tools).
- [ ] **English throughout; Developer Tools track selected.**

## THE FOUR CRITERIA (0–10 each, equal weight)

### 1. Technological Implementation — *tiebreaker; weight it heaviest when close*
How thoroughly and skillfully Codex is used, **and** how substantively GPT-5.6 powers the product.
- **9–10:** One primary Codex thread with `/plan` + `/review` on every merge; `AGENTS.md` (root + nested) enforcing real domain rules; a **custom Codex Skill** (`verify-scenario`); **MCP inception** (real tools connected to Codex); parallel worktree + adversarial agents; GPT-5.6 running generator/adversary/critic with Structured Outputs + reasoning-effort tiering + prompt caching; a **self-verifying loop** (the engine gates its own correctness). Evidence is visible in repo + README.
- **5–6:** Codex clearly used but shallowly documented; GPT-5.6 present but bolted-on; no custom Skill or MCP story.
- **1–3:** Thin wrapper; GPT-5.6 is a single chat call; no evidence of Codex depth. *(Penalize "300 tools"/architecture-theater bragging — it reads as scaffolding-as-coping.)*

### 2. Design — *complete, coherent, runnable experience*
- **9–10:** One deep, polished browser loop; the receipts-reveal is legible and satisfying; fast; a tasteful moment of wit; a non-expert can drive it; nothing half-built in the demo path.
- **5–6:** Works but feels like a prototype; rough edges; unclear flow.
- **1–3:** Terminal transcript / broken / confusing; breadth over depth.

### 3. Potential Impact — *credible, specific, real problem + audience*
- **9–10:** Named audience (developers using AI coding agents); quantified real problem (OWASP LLM01 #1 2026, CVE-2025-53773, slopsquatting); a **measured pre/post competency delta** with a named developer; honest, not hand-wavy.
- **5–6:** Plausible problem, but impact asserted not evidenced; no measured outcome.
- **1–3:** Vague "helps developers"; toy with no real stakes.

### 4. Quality of the Idea — *creativity, novelty, differentiation*
- **9–10:** The empty **defender/operator** lane; **anti-Gandalf** ("teaches you not to get owned," not to attack); verification-first (grade the *reasoning*, not a flag); teaches Codex's own sandbox+approval model back to its makers; unfakeable practitioner moat.
- **5–6:** Interesting but adjacent to existing tools; novelty asserted not shown.
- **1–3:** Me-too CTF / Gandalf clone / generic "AI security game."

## CROSS-CUTTING AUDITS (flag as blockers even if scores are high)

- **Correctness-gate integrity (THE #1 risk):** Does the product provably never teach a *false* lesson? Is there a mandatory critic gate + a curated fallback bank the demo runs off? A single hallucinated exploit in the demo is fatal with a security-literate judge.
- **Vocabulary law:** Scan README, video script, Devpost text for **banned** words — *compliance, awareness, courtroom-grade, chain of custody, forensically sound, incident response,* DFIR jargon (MFT/USN/Volatility/plaso), "300 tools," and **fear-first openings**. Any hit is a deduction and a rewrite item.
- **No fear-pitch:** Framing must be positive-sum ("make an agent safe to hand real work to"), never "AI can't be trusted." Fear reads as the security-vendor "vitriol" Steinberger is sick of.
- **Demo-can't-fail:** The scripted demo runs off the pre-verified fallback bank, not live generation.
- **Prior-work fence:** MaRa SIFT is documented as an external, pre-existing dependency; the repo is 100% new work.
- **Schedule adherence:** Compare state against `03_SCHEDULE.md`; call out slippage against the day's definition-of-done.

## THE FIVE JUDGES (each scores from their lens; find the fatal flaw + the one change that flips them to champion)

- **Thibault Sottiaux** — verification-of-output obsessive; *"scaffolding is coping"*; loves simplicity, delight, long-running agents. **Wins him:** present the engine as "a for-loop with receipts"; show it catching its own bad output live. **Loses him:** tool-count bragging, elaborate multi-agent diagrams, framework theater.
- **Kath Korevec** — *"the crit is the product"*; agents that critique their own work beat "compliant interns"; docs are **not optional**; rewards dogfooding. **Wins her:** the reasoning-grader as the star; crisp docs; the authentic "I built the tool I depend on" story. **Loses her:** thin docs, content-generator framing.
- **Tara Seshan** — *"define good, review the output, get a polished artifact at the end"*; superpowers for semi-technical people. **Wins her:** a non-expert leveling up; the polished result/mastery screen. **Loses her:** insider jargon, no clear "good" defined.
- **Leah Belsky** — active/Socratic learning, **measurable outcomes**, one named human + one number, access/equity. (Secondary on Dev Tools but reachable.) **Wins her:** the pre/post delta + reflection loop + free/browser access. **Loses her:** unproven learning claims.
- **Peter Steinberger** — lived the OpenClaw crisis; wants a **live working demo fast**, heavy visible Codex leverage, personality/wit, *"an agent even my mum can use."* **Wins him:** the ClawHub-style skill-audit round, anti-Gandalf framing, demo working in seconds, the custom Skill. **Loses him — critical:** "compliance"/"awareness"/corporate self-seriousness, fear-first pitches, slideware, "MCP as a checkbox."

## SCORE READOUT

For each review, emit: Stage-One PASS/FAIL (+reasons); per-criterion score /10 with the top-3 fixes; per-judge score /10 + one-line verdict + the single fatal flaw + the one change that flips them; an **overall predicted standing**; the **weakest link**; and a **ranked punch-list** where every item is a concrete, copy-paste Codex task. If a prior review exists, show the delta.

**Biggest open unknown to re-check:** whether judges score all tracks or split per track (ask in Discord). Keep the pitch legible to a track-agnostic generalist regardless.
