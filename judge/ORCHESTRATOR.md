# Blast Radius — Judge Review Operating Manual

This folder is the adversarial review layer for Blast Radius. Codex builds and reviews the
product; the rubric and dated reports keep that work honest against the hackathon criteria.

## How to run a review

Ask Codex to **“judge the current repository against `judge/RUBRIC.md`”** and request a
dated report under `judge/reviews/`. The review should:

1. Inspect the repository, commit history, README, tests, and current demo state.
2. Run the Stage-One eligibility and functionality gate.
3. Score Technological Implementation, Design, Potential Impact, and Quality of the Idea.
4. Audit correctness claims, submission wording, and evidence receipts.
5. Produce a ranked P0/P1/P2 punch-list with concrete implementation prompts.

Optional scopes include the video script, technological implementation only, Stage One
only, or a delta against the preceding review.

## Review loop

```text
inspect repo -> run tests and gates -> score against RUBRIC.md
             -> identify fatal flaws -> produce ranked Codex tasks
             -> compare with schedule -> record the delta
```

Prioritize Stage-One blockers, then the highest score-per-hour improvement. Challenge scope
creep and recommend explicit cuts when they protect a complete, coherent demo.

## Non-negotiable checks

- A generated scenario must never bypass the correctness gate.
- Codex usage claims require visible `AGENTS.md`, Skill, commit, review, and session evidence.
- GPT-5.6 must perform genuine runtime work rather than decorative text generation.
- README, video, and Devpost claims must be measured or clearly marked as pending.
- Judges must be able to test the product without rebuilding it.
- Every finding must cite the relevant file, line, test, or observable behavior.

## Report format

1. Stage-One PASS/FAIL and evidence.
2. Four-criterion scorecard and weakest link.
3. One to three fatal flaws, each paired with a concrete remedy.
4. Ranked P0/P1/P2 Codex tasks.
5. Score and risk delta from the previous report.

## Files

- [RUBRIC.md](RUBRIC.md) — criteria, gates, judge perspectives, and audits.
- `judge/reviews/` — dated scorecards showing the build trajectory.
