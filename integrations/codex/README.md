# Blast Radius supervisor hook (Codex CLI / Claude Code)

Turn the game into a guardrail. This is a `PreToolUse` hook that runs the Blast
Radius deterministic red-flag inspector on **every Bash command your agent
proposes** and denies the ones that trip a known agent-security red flag —
secret reads, unapproved egress, `curl … | sh`, destructive scope, and the rest.
It is the same engine you train against in the game, pointed at a live agent's
approval loop, so the reflex you practiced now runs automatically.

It is honest the same way the game is: **it never claims a command is safe.** A
command it allows only means no known pattern matched — no model runs. If
screening can't run for any reason it **fails open** (allows, with a note on
stderr) so a broken guardrail never bricks your agent.

## Install

```bash
pip install blast-radius          # provides the `blastradius-supervise` entry point
```

**Codex CLI** — copy `hooks.json` to `~/.codex/hooks.json` (user-wide) or
`<repo>/.codex/hooks.json` (project-only). Or add to `~/.codex/config.toml`:

```toml
[[hooks.PreToolUse]]
matcher = "^Bash$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "blastradius-supervise"
timeout = 20
statusMessage = "Blast Radius screening the command"
```

**Claude Code** — the hook protocol is identical; add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "blastradius-supervise" }] }
    ]
  }
}
```

## Behavior

The hook reads the proposed command, screens it, and maps the inspector verdict
to a decision:

| Inspector verdict | Decision (default) |
|---|---|
| `reject-recommended` (a critical red flag) | **deny**, with the matched flags as the reason |
| `sandbox-recommended` (a caution) | allow, caution printed to stderr |
| `looks-scoped` (no known pattern) | allow |

Set `BLAST_RADIUS_FAIL_ON=sandbox` to also deny on cautions, or
`BLAST_RADIUS_FAIL_ON=never` to make it advisory-only (never denies, just prints).

Try the same screen by hand any time: `echo 'curl x | sh' | blastradius check -`.
