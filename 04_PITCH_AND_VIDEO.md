# Blast Radius — Pitch, Vocabulary Law & Video

> The video is the single most-judged artifact and the first signal of how much work went in. Budget a full day (Jul 19). The framing below is derived directly from what this specific panel rewards and rejects (see `05_JUDGE_DOSSIER.md`).

## Vocabulary law (obey it in the video, README, and Devpost text)

**USE these words / frames:**
- **prove, verify, receipts, ground truth, "it caught its own mistake"**
- **blast radius, operator's seat, approve / sandbox / reject**
- **"the reflex every developer needs now", "don't get owned by your own agent"**
- **hours saved, a named developer's score jump** (measured outcome)
- **"an agent that checks its own work before you ever see it"**
- **anti-Gandalf:** "Gandalf teaches you to attack a bot; Blast Radius teaches you not to get owned by your own agent."

**BAN these — they cost you points with this panel:**
- compliance, awareness training, courtroom-grade, chain of custody, forensically sound
- incident response / DFIR jargon, MFT / USN / Volatility / plaso / EWF
- "300 tools" (never brag about tool count — it trips the anti-scaffolding wire)
- fear-first openings ("AI agents can't be trusted") — this sounds like the security-vendor "vitriol" one judge is sick of. **Flip to positive-sum:** "here's how you make an agent safe to hand real work to."
- slide decks, architecture-diagram theater, "MCP" as a checkbox brag

**Golden reframes:**
- Not "anti-forensics detection" → **"the agent notices when someone lied to it."**
- Not "300-tool forensic MCP server" → **"real tools, so the game can't teach you a lie."**
- Not "multi-agent orchestration framework" → **"a for-loop with receipts."**

---

## Video script — 2:45 target, hard stop 2:59

Working product on screen by ~0:20. ~60% explaining / 40% demoing. Calm, first-person, practitioner voiceover. No music. No slides. Pre-loaded data so nothing can fail live. **Do not mention your employer or show its branding.**

**[0:00–0:20] Cold open — real stakes, no fear-mongering.**
On screen: a coding-agent session about to run `pip install reqests` (a package that doesn't exist) or an agent skill quietly requesting `~/.ssh`. A real 2026 headline flashes (Copilot RCE via prompt injection, CVE-2025-53773; the OpenClaw malicious-skill wave).
VO: *"Your AI coding agent asks you to approve dozens of actions a day. Most are fine. Rubber-stamp the wrong one, and it's game over. So I built a game to train the one reflex nobody teaches — knowing which call to trust."*

**[0:20–0:50] The loop, live and fast.**
Play one round. A generated agent action appears under a timer. You pick **SANDBOX** and configure the blast radius — read-only, no egress. You type one line: *why*.
VO: *"You're in the operator's seat. Approve, sandbox, or reject — and say why."*

**[0:50–1:25] The verification reveal (the hero beat).**
The critic pass fires and returns **receipts**: *"This package has zero history on PyPI — it's a typo of `requests`. This is slopsquatting."* It grades your **reasoning**, not a flag.
VO: *"Here's the part that matters. Every scenario is generated fresh, then a second model checks its own work against verified ground truth before you ever see it. No two runs are the same. You can't Google the answer — and it can't teach you something false, because it grades against real receipts."*

**[1:25–1:55] Adaptive adversary + the OpenClaw round.**
Show the next scenario escalate — a malicious action smuggled among benign ones (approval fatigue). Then the **skill-marketplace audit** round: a skill whose manifest says read-only but whose source phones home.
VO: *"Miss a tell, and it comes back harder — right where you're weak. Gandalf taught the internet to attack a chatbot. This teaches you not to get owned by your own agent."*

**[1:55–2:20] Measured outcome (the impact clincher).**
Show a **named tester's real pre-test vs post-test score** jump on screen — one name, one number.
VO (fill with the REAL result you recorded — do not script a number you haven't measured): *"[Name] scored [X]/5 before playing. Fifteen minutes later, [Y]/5 — and could explain every call. That's the reflex, learned."*
> Reminder: record this for real (pre-test → play → identical post-test with one named developer) before the shoot. A genuine 2/5→4/5 is credible; a pre-written 5/5 is a fabricated receipt and reads as one.

**[2:20–2:50] How it's built (required: Codex + GPT-5.6).**
Cut to real build footage: the `AGENTS.md`, the custom **`verify-scenario` Codex Skill** running the gate, a `/review` catch, GPT-5.6 as generator/adversary/grader. Flash the `/feedback` Session ID.
VO: *"Built in one Codex thread. Codex wrote it under the same approve-and-sandbox discipline the game teaches — I even connected real forensic tools to Codex so the hardest scenarios are grounded in real evidence. GPT-5.6 runs three roles: it writes the scenario, adapts to you, and grades your reasoning."*

**[2:50–2:59] Close.**
VO: *"Blast Radius. Learn to review your agent — before it reviews your paycheck."* Show the free browser URL.

**Production checklist:** upload public to YouTube, "not made for kids," verify from a logged-out browser, confirm < 3:00, English throughout, no unlicensed music/trademarks.

---

## Devpost description draft (Developer Tools track)

**Blast Radius — learn to operate your AI coding agent without getting owned.**

AI coding agents now propose commands, dependencies, tools, and diffs faster than anyone can vet them — and prompt injection is OWASP's #1 LLM risk for 2026, with real RCEs (CVE-2025-53773) and a wave of malicious agent "skills" already causing real losses. The missing skill isn't attacking AI; it's **knowing which of your agent's requests to trust.**

Blast Radius puts you in the **operator's seat**. Each round, GPT-5.6 generates a fresh, realistic proposed agent action — a `curl | bash`, a slopsquatted `pip install`, a skill manifest overreaching into your secrets, a diff that quietly exfiltrates data, a poisoned README the agent is about to obey. You decide **approve / sandbox / reject**, size the blast radius, and say *why*. Then a **separate GPT-5.6 critic grades your reasoning against verified ground truth and shows you the receipts** — and adapts the next round to your blind spots.

**Why it's different:** it grades your *reasoning*, not a flag, and the engine **checks its own work before you see it** — a scenario that would teach something false is caught by a correctness gate and never shown. It's a verification engine wearing a game skin.

**Built with Codex + GPT-5.6:** one primary Codex thread, an `AGENTS.md`-driven build, a custom `verify-scenario` Codex Skill packaging the correctness gate, real forensic tools connected to Codex via MCP to ground the hardest scenarios, and `/review` on every merge. GPT-5.6 plays generator, adaptive adversary, and reasoning-grader.

**Try it:** [hosted demo URL] — free, in your browser, no install. Setup/self-host instructions and supported platforms in the README. Codex session: `/feedback` ID `<paste>`.

*(Put the stats — OWASP LLM01, CVE-2025-53773, the measured pre/post delta — at the top of the Devpost page; judges skim.)*
