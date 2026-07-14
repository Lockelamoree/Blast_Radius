# Blast Radius — Judge Dossier

> Five judges, all OpenAI product/eng leadership. The panel's **single strongest shared taste is verification of agent output** — which is exactly what Blast Radius is. Security *jargon* is the only real liability; the concept itself is on-message. Full profiles in `research/02_judge_sentiment.json`.

## The one-line read
They just gave their last hackathon (Feb 2026) to a system whose differentiator was a **verification/decision layer** — judged, in part, by two of these same five. You are holding the winning thesis. Don't bury it under forensics vocabulary.

## Biggest open unknown
Whether judges **score all tracks** or the panel **splits per track**. Not documented. **Ask in Discord on Day 0.** Regardless: keep the pitch legible to a non-security, non-education generalist — the mechanism (generate → verify → grade with receipts) must land in 15 seconds without a security background.

---

## The primary trio (Developer Tools lands hardest here)

### Thibault Sottiaux — Head of Product & Platform (ex-Codex eng lead)
- **Loves:** verification of agent output (co-authored OpenAI's "verify code at scale" post; every OpenAI PR is Codex-reviewed as a "safety net"); **simplicity over scaffolding** ("scaffolding is coping"); delight/polish; sandboxing.
- **Show him:** the critic gate + receipts as *"a for-loop with receipts."* The live money shot of the engine catching its own bad output. A polished, fast UI.
- **Avoid:** bragging about tool count or an elaborate multi-agent diagram. He reads heavy harness as hiding weak models.

### Kath Korevec — Codex PM
- **Loves:** *"the crit is the product"* — agents that critique their own work beat "compliant interns"; docs are **not optional**; rewards builders who **felt the pain themselves**.
- **Show her:** the reasoning-grader (literally a crit loop); a crisp `AGENTS.md` + README; your authentic dogfooding story (you build and depend on the real tools).
- **Avoid:** thin docs, "content generator" framing (that's the compliant-intern pattern she dislikes).

### Peter Steinberger — MTS, creator of OpenClaw
- **Lived** the OpenClaw crisis: 1000+ malicious skills, prompt injection, RCE, ~$2.3M stolen, tens of thousands of exposed instances. Responded with scanning + a threat model.
- **Loves:** a **live working demo, fast**; heavy visible Codex leverage; agents that **close their own loop**; personality/wit; *"an agent even my mum can use."*
- **Show him:** the **skill-marketplace audit round** (his exact scar, as practice); the anti-Gandalf framing; the live demo working in seconds; the custom Codex Skill.
- **Avoid — critical:** "compliance," "awareness," corporate self-seriousness, and **fear-first pitches** (they sound like the security-vendor "vitriol" he's sick of). Keep it positive-sum and playful. Never slideware.

## Strong secondaries

### Tara Seshan — Product staff (ex-Stripe/Watershed)
- **Loves:** *"define what good looks like, review the outputs, get a polished artifact at the end"*; giving **semi-technical people superpowers**.
- **Show her:** the review-the-agent loop and the polished result/mastery screen; a non-expert playing it and leveling up.

### Leah Belsky — VP Education (ex-Coursera CRO)
- Owns the Education lens, but reachable from Dev Tools via impact. **Loves:** active/Socratic learning, **measurable outcomes**, one **named human + one number**, access/equity.
- **Show her:** the **pre/post score delta** with a named tester; the reflection loop; free + browser-based = access. This is why we kept the measured outcome even off her track.
- **Avoid:** claiming learning gains without showing the number.

---

## What every judge must see in the first 30 seconds
1. A **working product**, in the browser, fast.
2. The **verification reveal** — receipts, and the engine grading *reasoning*, not a flag.
3. That it's **generated fresh + self-checked** (novel, un-Googleable, can't teach a lie).
4. Zero fear-mongering, zero jargon, one moment of wit.

## Scorecard we're playing for (well-framed)
- **Technological Implementation (tiebreaker):** the self-critiquing engine + heavy, visible Codex craft (AGENTS.md, custom Skill, MCP inception, `/review`). This is where we win the tie.
- **Design:** one coherent, polished, runnable loop with receipts.
- **Potential Impact:** OWASP #1 threat + a measured competency delta + a named developer.
- **Quality of Idea:** the empty defender lane, anti-Gandalf, teaching Codex's own safety model back to its makers.
