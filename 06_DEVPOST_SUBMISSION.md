# Blast Radius — Devpost Submission Copy

> Name, tagline, description, and thumbnail — all tuned to the four judging criteria and the panel's documented taste (verification-first, delight, live demo, no fear/compliance vocabulary). Paste these into the Devpost fields; the thumbnail is in `assets/`.

## Project name

### ✅ **Blast Radius**  *(recommended)*
"Blast radius" is already a developer/SRE term — the scope of damage a change or failure can cause. That's exactly the skill the game teaches: **size the damage before you approve.** It's in your judges' native vocabulary (ex-Codex/infra leaders), it's punchy and a little dangerous without being fear-mongering, and it reads at thumbnail size. No "compliance," no "training," no jargon.

**Backup names** (in case of a Devpost collision):
- **Receipts** — leans on the "every verdict shows receipts" hook; short, memeable.
- **Rubber Stamp** — names the anti-pattern the game cures (approving without thinking); ironic, memorable.

## Tagline (Devpost "tagline" field — one line)

> **Learn to operate your AI coding agent — before it burns you.**

Alt: *"The game that trains the one reflex AI coding agents demand: knowing which call to trust."*

---

## Elevator pitch (≤200 words — this version is 186)

> Your AI coding agent proposes dozens of actions a day — shell commands, new dependencies, tools to install, diffs to merge — and asks you to approve them. Approve the wrong one and you're owned. Prompt injection is now the #1 LLM risk, with real CVEs and stolen credentials to prove it, yet nobody teaches the reflex that stops it: knowing which of your agent's requests to trust.
>
> **Blast Radius** makes that reflex playable. It drops you in the operator's seat: each round, GPT-5.6 generates a fresh, realistic agent-action; you decide **approve, sandbox, or reject** — and type one line on *why*. A separate GPT-5.6 critic then grades your reasoning against verified ground truth and shows the receipts (this package isn't on PyPI; this tool's manifest contradicts what it does), adapting the next round to your blind spots.
>
> It grades your thinking, not a flag — and it checks its own work before you see it, so it can't teach you something false. Gandalf taught the internet to attack a bot; Blast Radius teaches you not to get owned by your own agent. Built with Codex. Free, in your browser.

---

## Full description (maps to Devpost's standard section fields)

> ⚠️ **DRAFT — this is the *target* copy. Do not submit any sentence until it is true.** The "How I built it" and "Accomplishments" sections are written as the story you intend to be able to tell by July 20. Before submitting: switch build claims to accurate tense, fill every `<placeholder>` with a real value (Session ID, hosted URL, the measured delta), and **never state a number you have not actually measured.** The judging panel will treat a fabricated receipt as disqualifying.

**Inspiration**
Prompt injection is OWASP's #1 LLM risk for 2026, and it's not theoretical anymore: a Copilot RCE via prompt injection (CVE-2025-53773), a wave of malicious agent "skills" stealing credentials, `pip install` suggestions for packages that don't exist until an attacker registers them. AI coding agents now propose actions faster than anyone can vet them, and the missing skill isn't attacking AI — it's **knowing which of your agent's requests to trust.** Nobody was teaching that reflex, so I built a game for it.

**What it does** *(Design + Quality of Idea)*
Blast Radius drops you into the operator's seat of a coding agent. Each round, a realistic proposed action appears under a mild timer that mimics real approval fatigue — a `curl | bash`, a slopsquatted dependency, a tool manifest quietly reaching for your `~/.ssh`, a diff that adds a data-exfil call, a poisoned README the agent is about to obey. You choose **approve / sandbox / reject**, size the blast radius, and type one line on *why*. Then the verdict: **receipts** (concrete, checkable facts — "this package has zero history on PyPI; it's a typo of `requests`"), a Socratic explanation of what the attack would have done and what stops it, and an adaptive next round that targets whatever you just missed. Two extra round types go deeper: a **skill-marketplace audit** (inspect a tool's manifest vs. what it actually does) and a **forensic-triage** round backed by real security tooling. Everything runs free in the browser — no install.

**How I built it** *(Technological Implementation — the tiebreaker)*
Built in a single primary Codex thread. An `AGENTS.md` encodes the one rule that makes the whole thing trustworthy — *never show a scenario that hasn't passed the correctness gate* — and I packaged that gate as a **custom Codex Skill** (`verify-scenario`) that I reused to bulk-verify the scenario bank. I connected a real forensic MCP server to Codex during development so the hardest scenarios are grounded in genuine tool output — the agent that built the game used real tools to keep it honest. The UI was built by a parallel Codex worktree agent while the engine progressed, and a second adversarial agent tried to sneak wrong answers past the grader; every hole it found became a test. `/review` ran before every merge — fitting, since the product itself teaches reviewing agent output. **GPT-5.6 plays three roles:** generator (fresh, non-Googleable scenarios via Structured Outputs), adaptive adversary (targets your blind spots), and critic-grader (a separate, max-reasoning pass that gates scenario correctness *and* grades your free-form reasoning with receipts).

**Challenges I ran into**
The core risk was correctness: a game that teaches a *hallucinated* exploit is worse than no game. So the engine never free-invents a vulnerability — it only generates bounded variations on a hand-verified template spine (OWASP LLM Top 10, real CVE patterns, documented slopsquatting data), and the critic pass is a mandatory gate that discards anything it can't prove, falling back to a curated, pre-verified bank. Getting the grader to score *reasoning* (not a flag string) reliably was the hard, interesting part.

**Accomplishments I'm proud of** *(Potential Impact)*
It measurably teaches. A short pre-test and identical post-test bracket each session. `<INSERT REAL, MEASURED pre→post result from ONE named tester — e.g. "went from 2/5 to 4/5" — only after you have actually run and screen-recorded it. Do NOT invent this number.>` It grades reasoning, not clicks, and it can't teach you something false, because every verdict is backed by a receipt.

**What I learned**
That the most compelling thing an AI product can do is **check its own work before you see it** — and that the same generate-then-verify loop that makes the game trustworthy is the loop developers now need in their heads every day.

**What's next**
The citation-and-verification engine is domain-agnostic: the same "prove it against ground truth" core could sit under any agent doing high-stakes work.

**Built with**
Codex · GPT-5.6 (Structured Outputs, reasoning-effort control, prompt caching) · MCP · a web frontend · (list the exact stack Codex chooses).

**Try it**
Hosted demo: `<URL>` — free, in your browser, no install. Setup/self-host instructions and supported platforms are in the README. Codex session: `/feedback` ID `<paste>`.

*(Put the stat line — OWASP LLM01, CVE-2025-53773, the 2/5→5/5 delta — at the very top; judges skim.)*

---

## Thumbnail

**Ship: `assets/thumbnail.png`** (= the "Decision Card", `thumb_decision.svg`) — **1200×800, exact 3:2**, Devpost's project-gallery ratio (JPG/PNG/GIF, 5 MB max). Research-backed choice: ~90% of gallery cards are raw screenshots or Devpost's default placeholder, so a purpose-composed, **type-driven** hero frame wins on contrast before craft even registers. It shows the game's *verb* — a GPT-5.6 proposal (`pip install reqeusts`, "not on PyPI") over three big color-coded chips **APPROVE / SANDBOX / REJECT** with a cursor frozen over the hot REJECT — so the whole story survives down to ~120px (the mobile-grid crop) even if the code line blurs to texture. Near-black terminal ground, heavy monospace, one warm coral accent, no fear/lock/klaxon/compliance clichés — native to the DevDay/Linear/Vercel aesthetic these judges reward.

**Alternate / 2nd gallery slide: `assets/thumb_verdict.png`** (the "Verdict Stamp") — a giant green **GOOD CALL** + check with a faint `REJECTED` counter-stamp; leads with the graded-verdict "receipts" reward. Pairs with the Decision Card as a two-beat story (you decide → you get graded). Both use one locked type system + palette + bottom-left wordmark. Regenerate the PNG after editing the SVG (this machine has chromium, not rsvg):
```bash
cd assets && printf '<!doctype html><meta charset=utf-8><style>html,body{margin:0;background:#0A0E14}svg{display:block}</style>' > _w.html && cat thumbnail.svg >> _w.html
chromium-browser --headless=new --disable-gpu --no-sandbox --user-data-dir=$(mktemp -d) \
  --window-size=1200,800 --hide-scrollbars --screenshot=thumbnail.png "file://$PWD/_w.html" && rm _w.html
```
Or just open `thumbnail.svg` in any browser and screenshot. Devpost accepts the PNG directly (1200×800, 3:2).
