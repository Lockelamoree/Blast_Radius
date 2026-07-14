# Blast Radius — Schedule (July 13 → 21, Berlin time)

> Solo, near-full-time. Every day has a **goal**, the **Codex work** (prompts in `02_CODEX_PLAYBOOK.md`), a **definition of done**, and a **fallback cut** if you're behind. The ordering is deliberate: **the make-or-break correctness engine is built first**, so if anything slips it's polish, never trust.

**Hard stop:** submissions close **02:00 Berlin, July 22** (= July 21, 5:00 PM PDT). **Target submission: July 20.** Credits form: **July 17, 21:00 Berlin.** Judge demo must stay live through **Aug 5**.

---

## Jul 13 (Mon) — Lock-in day
**Goal:** access sorted, repo alive, first real code committed.
- Do the **Day 0 human checklist** in `00_README_START_HERE.md` (accounts, API key + spend cap, **credits form**, Devpost + Discord, start screen-recording, VPS, repo + license).
- Open **the primary Codex thread**. Run `/plan` on the whole build from `01_PRODUCT_SPEC.md`.
- Paste **AGENTS.md** (root + nested). **WP1**: scaffold repo + commit the **data model** (§8).
- **DoD:** repo public + licensed; data-model types + tests committed; AGENTS.md in place; screen recording running.
- **Fallback cut:** if access stalls, still commit AGENTS.md + data model by hand so Day-1 history exists.

## Jul 14 (Tue) — The trust engine (THE critical day)
**Goal:** prove the engine cannot teach a lie.
- **WP2**: verified template **spine** + curated **fallback bank** (~15–20 scenarios) + **critic correctness gate** (via the `verify-scenario` Skill). Write the test that feeds a known-bad scenario and asserts rejection.
- Begin **WP3**: reconcile GPT-5.6 model IDs/features against live docs; wire the critic.
- **DoD:** gate blocks known-bad scenarios in tests; every bank scenario passes the gate and has tells + receipts + citation.
- **Fallback cut:** if generation isn't wired, the **hand-curated bank + gate alone** is enough to demo — ship that first.

## Jul 15 (Wed) — The loop comes alive
**Goal:** a full session plays headless.
- Finish **WP3** (generator + adversary). **WP4**: five action families, APPROVE/SANDBOX/REJECT + blast-radius config, one-line reasoning, reasoning-first grading, adaptation.
- **DoD:** headless test runs pre-test → rounds → post-test → LearnerProgress with a delta; receipts on every verdict.
- **Fallback cut:** ship 3 of 5 action families (dangerous command, poisoned dependency, over-scoped manifest); defer malicious-diff + poisoned-context.

## Jul 16 (Thu) — Fold-ins + UI in parallel
**Goal:** breadth + a clickable face.
- **WP5**: skill-marketplace audit round + forensic-triage round (MaRa SIFT oracle).
- **WP6** in a **parallel Codex worktree agent**: the browser UI (§9).
- Kick off the **adversarial agent** (verify the verifier).
- **DoD:** both fold-in rounds pass the gate + grade; UI plays the fixed demo path (§10) off the bank.
- **Fallback cut:** ship only the **skill-marketplace** fold-in (higher judge resonance); keep forensic-triage as a stretch. UI can be minimal-but-clean.

## Jul 17 (Fri) — Pedagogy + hosting (⏰ credits form 21:00)
**Goal:** measurable outcome + judges can play it.
- Wire **pre/post test** + reflection loop + mastery/competency screen.
- **WP7**: deploy the **one-click, pre-loaded, spend-capped judge demo** to the VPS; write **install/setup instructions + supported platforms** (Dev Tools requirements #7–9).
- Run a **clean-baseline** pass (a benign scenario the player should APPROVE) to prove low false-positives.
- **DoD:** logged-out browser plays the demo with zero setup; pre/post delta shows on screen.
- **Fallback cut:** if hosting fights you, ship a rock-solid `docker compose up` / one-command local run + a short Loom as backup, but keep pushing for the hosted URL (it's a Dev Tools requirement).

## Jul 18 (Sat) — Feature freeze + words
**Goal:** no new features; everything written.
- **WP8**: `/review` the whole codebase, fix findings. Write the **README** ("Built with Codex" + "Prior work vs. new work") and the **Devpost description** (`04_PITCH_AND_VIDEO.md`).
- Full **rehearsal** of the demo path; fix anything that stutters.
- **DoD:** `/review` clean; README complete; demo path runs flawlessly twice in a row.
- **Fallback cut:** none — freezing is the cut. Protect this day.

## Jul 19 (Sun) — Video day
**Goal:** the 2:45 video (your single most-judged artifact).
- Script from `04_PITCH_AND_VIDEO.md`; assemble build-week screen recordings; record calm first-person voiceover; nail the **verification money shot** and the **pre/post delta**.
- **DoD:** a rough cut under 3:00 exists by end of day.
- **Fallback cut:** if editing runs long, a clean single-take screencapture with voiceover beats a fancy edit that isn't done.

## Jul 20 (Mon) — SUBMIT (a full day early)
**Goal:** submitted and confirmed.
- Final video edit; upload to **YouTube (public, "not made for kids")**; verify from a **logged-out** browser; confirm < 3:00.
- Run **`/feedback`** in the primary Codex thread → paste the **Session ID** into Devpost.
- Walk the **compliance table** (`00_README_START_HERE.md`) top to bottom, including Dev Tools extras. Submit on Devpost; confirm receipt.
- **DoD:** submission confirmed; every compliance row green.

## Jul 21 (Tue) — Buffer + hostile re-test
**Goal:** be the judge who's trying to break it.
- Fresh browser: click the YouTube link, play the hosted demo, clone the repo and follow the README from scratch. Fix any friction before 02:00 Jul 22.
- Snapshot/back up the VPS deployment.

## Jul 22 → Aug 5 — Uptime watch
- Keep the demo live and monitored the entire judging window. A dead link on July 30 loses the Design criterion. Set an uptime alert.

---

## If you fall behind, cut in this order
1. Second fold-in (forensic-triage) → stretch goal.
2. Action families 4–5 (malicious-diff, poisoned-context) → ship 3.
3. Adversary adaptation → static difficulty ramp is fine for the demo.
4. Fancy UI animation → clean and fast beats flashy.

**Never cut:** the correctness gate, the receipts, the fixed demo path off the bank, the hosted judge URL, the video, the `/feedback` Session ID.
