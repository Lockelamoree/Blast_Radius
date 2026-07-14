# Ubuntu VPS deployment

Point a public DNS record at an Ubuntu VPS, then run from a clone:

```bash
sudo OPENAI_API_KEY='spend-capped-key' bash deploy/deploy.sh blast-radius.example.com
```

The script installs Python, Caddy, and the app; creates the restricted service user;
enables both services; obtains HTTPS through Caddy; and verifies `/healthz`. It preserves an
existing `/etc/blast-radius.env`, so key rotation and budget changes remain operator-owned.

The public profile keeps `BLAST_RADIUS_LIVE_GENERATION=false`: a server-side key enables
GPT-5.6 reasoning grading, while scenario generation stays deterministic. Set
`BLAST_RADIUS_DAILY_LLM_BUDGET` to cap model calls per UTC day; once exhausted, the app
continues with deterministic grading.

## Manual deployment

1. Create an unprivileged `blast-radius` service account and clone this repository into
   `/opt/blast-radius`.
2. Create the environment and install the locked project interface:

   ```bash
   cd /opt/blast-radius
   python3 -m venv .venv
   .venv/bin/python -m pip install .
   ```

3. Create `/etc/blast-radius.env` owned by root and readable by the service group:

   ```dotenv
   BLAST_RADIUS_DATABASE=/opt/blast-radius/blast_radius.db
   BLAST_RADIUS_LIVE_GENERATION=false
   BLAST_RADIUS_SESSION_TTL_MINUTES=180
   BLAST_RADIUS_DAILY_LLM_BUDGET=100
   OPENAI_API_KEY=spend-capped-server-side-key
   ```

4. Copy `blast-radius.service` to `/etc/systemd/system/`, run
   `sudo systemctl daemon-reload`, then enable and start it.
5. Replace the hostname in `Caddyfile`, install Caddy from its official repository, copy
   the configuration to `/etc/caddy/Caddyfile`, and reload Caddy.
6. Verify `https://your-host/healthz` and complete a full run in a logged-out browser.

Do not enable live generation until the deterministic demo has passed its rehearsal and a
spend-capped server-side API key is configured.
