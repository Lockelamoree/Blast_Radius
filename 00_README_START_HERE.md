# Blast Radius — Original planning package

> **Historical planning material imported on July 14, 2026.** The implemented product,
> supported setup, current scope, and truthful submission status live in `README.md`.
> MaRa/forensic triage is not part of the current implementation. Unfilled claims and
> example measurements in this package are not observed results.

> **This folder is your Build Week battle plan.** It is written to be handed to **Codex** as the source of truth for building **Blast Radius**, our entry for **OpenAI Build Week** (Developer Tools track). Read this file top-to-bottom once, do the **Day 0 human checklist** below (Codex can't do these), then open Codex and follow `02_CODEX_PLAYBOOK.md` + `03_SCHEDULE.md`.

## What we're building, in one paragraph

**Blast Radius** is a browser game that puts you in the **operator's seat of an AI coding agent**. Every round, GPT-5.6 generates a fresh, realistic *proposed agent action* — a shell command, a suggested dependency, an MCP/skill manifest, a code diff, a poisoned README the agent is about to obey — and you decide **APPROVE / SANDBOX / REJECT** (and configure the blast radius) under a mild timer that mimics real approval fatigue. Then a **separate GPT-5.6 critic pass grades your reasoning against verified ground truth and shows you the receipts** (why that package doesn't exist on PyPI, why that manifest's declared scope contradicts its network calls). It teaches the one reflex every developer now needs: *don't get owned by your own agent.* Two extra round types deepen it — a **skill-marketplace audit** (the OpenClaw supply-chain scenario) and a **forensic-triage** round backed by real tool output.

The whole thing is a **verification engine wearing a game skin** — which is exactly the artifact class this judging panel rewards.

## The documents in this folder (read in this order)

| # | File | What it's for |
|---|------|---------------|
| 0 | `00_README_START_HERE.md` | This file — orientation, Day 0 human checklist, compliance table |
| 1 | `01_PRODUCT_SPEC.md` | Exactly what Blast Radius is: rounds, engine, data model, UI, demo, cut list |
| 2 | `02_CODEX_PLAYBOOK.md` | How to drive Codex to max the "Technological Implementation" score; paste-ready AGENTS.md, SKILL.md, and per-task prompts |
| 3 | `03_SCHEDULE.md` | Day-by-day plan, July 13→21 (Berlin time), with a fallback cut each day |
| 4 | `04_PITCH_AND_VIDEO.md` | Vocabulary law, the 2:45 video script, Devpost description draft |
| 5 | `05_JUDGE_DOSSIER.md` | Who judges you and what each one needs to see |
| — | `research/` | The raw research this plan is built on (rules, judge profiles, landscape) |

## The one thing that decides everything

Judging has **4 equally-weighted criteria**, and **ties break on Technological Implementation (how skillfully you used Codex) first.** So the tiebreaker is *Codex proficiency*. That's why `02_CODEX_PLAYBOOK.md` matters as much as the code: your Codex session transcript, your `AGENTS.md`, your custom Skill, and your README "Built with Codex" chapter are **judged artifacts**, not backstage plumbing. Treat them that way from hour one.

The four criteria (all equal weight):
1. **Technological Implementation** — how thoroughly/skillfully Codex is used. *(Tiebreaker.)*
2. **Design** — a complete, coherent, runnable product experience.
3. **Potential Impact** — a credible, specific case for a real problem + audience.
4. **Quality of the Idea** — creativity, novelty, differentiation.

---

## DAY 0 HUMAN CHECKLIST (today, July 13 — do these before/while Codex starts)

These are the things **only you** can do. Order matters. Times are **Berlin (CEST)**.

### A. Access & money (blocks everything — do first)
- [ ] **ChatGPT plan with Codex enabled.** Subscribe to a plan that includes Codex (Plus/Pro). Confirm you can open a Codex session in ChatGPT.
- [ ] **OpenAI API key** at platform.openai.com → create key → **add billing** → **set a hard monthly spend cap** (e.g. €50) so a runaway loop can't drain you. Blast Radius calls GPT-5.6 from its own backend, so the product needs an API key separate from your Codex subscription.
- [ ] **Verify GPT-5.6 API access.** Make one tiny test call (any model in the `gpt-5.6` family) and confirm it returns. If the exact model IDs differ from what the spec assumes (`gpt-5.6` / sol/terra/luna tiers), note the real IDs — Day 1 reconciles them against live docs.
- [ ] **⏰ Request the $100 Codex credits** via the Build Week form. **Deadline: July 17, 12:00 PM PT = 21:00 Berlin.** Do it today; don't let billing stall the build.

### B. Registration & intelligence
- [ ] **Register on Devpost** for OpenAI Build Week (openai.devpost.com) and **select the Developer Tools track** on your submission draft.
- [ ] **Join the hackathon Discord.** Ask two questions in the appropriate channel and screenshot the answers:
  1. *"Do judges score all tracks, or is the panel split per track?"* (This is our biggest open unknown — see `05_JUDGE_DOSSIER.md`.)
  2. *"How is the `/feedback` Codex Session ID field validated — does it need to be public/shared?"*
- [ ] Skim any kickoff livestream/office-hours for organizer emphasis; note anything that changes our read.

### C. Build hygiene (start now, thank yourself later)
- [ ] **Start screen-recording every Codex session from minute one.** The video (July 19) needs real build footage: the `/plan`, the custom Skill wrapping tools, the `/review` catches. You cannot re-shoot these later. Record continuously; trim later.
- [ ] **Create the public GitHub repo** now, with an OSI license (MIT or Apache-2.0). This repo is *new work* — MaRa SIFT stays a **documented external dependency**, never copied in.
- [ ] **Rent a small VPS** (any provider, ~€20–40 for the window) for the judge-testable demo. You'll deploy to it ~July 17 and it must **stay up through August 5**. Put a spend-capped API key on it.
- [ ] **YouTube account** ready for a public upload (July 20).

### D. Personal due diligence (do not skip)
- [ ] **Keep this project 100% personal.** No employer data, hardware, branding, credentials, or work hours. The demo case uses synthetic/public data only.
- [ ] **Check your employer's side-project / invention policy** and German employee-invention law (*Arbeitnehmererfindungsgesetz*). You are *eligible* under the hackathon rules (only OpenAI/Devpost employees are excluded), and you keep IP — but internal policy is a separate matter. Resolve it before submitting. **Never mention your employer in the repo, video, or submission.**

---

## SUBMISSION COMPLIANCE TABLE

Every hard requirement from the rules, where it gets satisfied, and when. **Developer Tools has extra requirements** (marked ⚙️) that most tracks don't. Green-light the whole table before submitting on July 20.

| # | Requirement | Where it's satisfied | Owner | Target date |
|---|-------------|----------------------|-------|-------------|
| 1 | Project **built with Codex AND GPT-5.6** (both required) | Codex builds it; GPT-5.6 runs the generator/adversary/critic engine | You + Codex | Jul 13–18 |
| 2 | **Public YouTube demo video, < 3:00**, with audio, showing what you built **and how you used Codex + GPT-5.6** | `04_PITCH_AND_VIDEO.md` script | You | Jul 19–20 |
| 3 | **Public repo** with an OSI **license** | GitHub repo created Day 0 | You | Jul 13 |
| 4 | **README describing how you collaborated with Codex** | "Built with Codex" chapter — template in `02_CODEX_PLAYBOOK.md` | Codex + you | Jul 18 |
| 5 | **`/feedback` Codex Session ID** from the thread where most core functionality was built | Run `/feedback` in the primary Codex thread; paste ID into the Devpost field | You | Jul 20 |
| 6 | **Judge-testable access, live through Aug 5** | Hosted VPS demo, one-click, pre-loaded | You | Deploy Jul 17; watch to Aug 5 |
| 7 ⚙️ | **Installation / setup instructions** (Dev Tools) | README "Run it yourself" section + repo | Codex + you | Jul 17–18 |
| 8 ⚙️ | **Supported platforms** stated (Dev Tools) | README (browser + which OS/runtime for self-host) | Codex + you | Jul 18 |
| 9 ⚙️ | **Judges can test WITHOUT rebuilding** (Dev Tools) | Hosted demo URL (no build needed) + credentials if gated | You | Jul 17 |
| 10 | **Everything in English** | All docs, video, README | You | throughout |
| 11 | **One track selected: Developer Tools** | Devpost submission form | You | Jul 13 draft |
| 12 | **New-work documentation** (MaRa SIFT is pre-existing dep) | README "Prior work vs. new work" section + dated commits | Codex + you | Jul 18 |

**Submit July 20 (a full day early).** The hard stop is **02:00 Berlin on July 22**. Do not be the person debugging at the deadline.

## What Codex should do first

Open `02_CODEX_PLAYBOOK.md`, then `03_SCHEDULE.md` (Jul 13 block). The very first build task is **not** the game — it's the **verified scenario spine + the critic correctness gate + a curated fallback scenario bank** (Days 1–2). That is the make-or-break: a game that teaches a *hallucinated* exploit loses instantly with a security-literate judge, so we prove the engine can't lie before we build anything on top of it.
