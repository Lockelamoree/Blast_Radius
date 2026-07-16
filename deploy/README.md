# Ubuntu 24.04 LTS VPS deployment

Point a public DNS record at the VPS, start from a fresh trusted clone, and use the silent
prompt so the key value is not written to shell history:

```bash
sudo BLAST_RADIUS_PROMPT_FOR_OPENAI_KEY=1 bash deploy/deploy.sh blast-radius.example.com
```

The script requires Python 3.11+, builds a fresh root-owned release under
`/opt/blast-radius-releases`, installs it non-editably, and atomically points
`/opt/blast-radius` at that release. The service user can write only
`/var/lib/blast-radius`; it cannot alter source, the virtual environment, deployment helpers,
or systemd/Caddy configuration. On re-runs the script preserves the existing key unless a
key is explicitly supplied or prompted, in which case it is updated. An empty explicitly
supplied `OPENAI_API_KEY` clears it. A deployment with an unverified critic fails after
printing sanitized recent service logs. Use `BLAST_RADIUS_ALLOW_DEGRADED_DEPLOY=1` only for
an intentional deterministic-only deployment.

The default proof profile keeps `BLAST_RADIUS_LIVE_GENERATION=false`: a server-side key enables
GPT-5.6 Sol tell matching, while scenario selection stays deterministic. After the genuine
Sol receipt is captured, set `BLAST_RADIUS_LIVE_GENERATION=true` explicitly to enable
verified-anchored Luna presentation reskinning. Generated rounds remain deterministically
graded and fall back to the unchanged anchor on any gate or provider failure. Set
`BLAST_RADIUS_DAILY_LLM_BUDGET` to cap model calls per UTC day; once exhausted, the app
continues with deterministic grading. The default budget is 500 provider-dispatched attempts;
timeouts and provider errors still count because they can incur usage.

## Manual deployment

1. Create an unprivileged `blast-radius` service account, a root-owned release directory,
   and a separate writable state directory:

   ```bash
   sudo install -d -m 755 -o root -g root /opt/blast-radius-releases
   sudo install -d -m 750 -o blast-radius -g blast-radius /var/lib/blast-radius
   ```

2. Clone an exact trusted revision into a root-owned release, verify the origin/revision and
   clean status, create its virtual environment, and install with `python -m pip install .`
   (never editable). Point `/opt/blast-radius` at the finished release only after validation.
3. Create `/etc/blast-radius.env` mode `0600`, owned by root:

   ```dotenv
   BLAST_RADIUS_DATABASE=/var/lib/blast-radius/blast_radius.db
   BLAST_RADIUS_LIVE_GENERATION=false
   BLAST_RADIUS_SESSION_TTL_MINUTES=180
   BLAST_RADIUS_DAILY_LLM_BUDGET=500
   BLAST_RADIUS_CRITIC_TIMEOUT_SECONDS=8
   BLAST_RADIUS_GENERATION_TIMEOUT_SECONDS=8
   BLAST_RADIUS_SESSION_LLM_CALL_CAP=12
   BLAST_RADIUS_GENERATED_ROUNDS_PER_SESSION=5
   BLAST_RADIUS_GENERATOR_MAX_OUTPUT_TOKENS=4096
   BLAST_RADIUS_GATE_MAX_OUTPUT_TOKENS=4096
   BLAST_RADIUS_REASONING_MAX_OUTPUT_TOKENS=2048
   BLAST_RADIUS_REVISION=the-deployed-git-commit
   OPENAI_API_KEY=spend-capped-server-side-key
   ```

4. Keep the application checkout and virtual environment root-owned/read-only. Copy
   `blast-radius.service` to `/etc/systemd/system/`, run
   `sudo systemctl daemon-reload`, then enable and start it.
5. Replace the hostname in `Caddyfile`, install Caddy from its official repository, copy
   the configuration to `/etc/caddy/Caddyfile`, and reload Caddy.
6. Verify `https://your-host/healthz` and complete a full run in a logged-out browser.

Do not enable live variation until the deterministic deployment has produced and cross-checked
a genuine Sol reasoning-grade receipt. Enabling it does not enable model-authored truth or
new evidence; it only activates the gated, verified-anchor presentation path.

After `/healthz` reports `reasoning_grading: "live"`, capture one real reasoning grade:

```bash
python scripts/capture_live_grade.py https://your-host
```
