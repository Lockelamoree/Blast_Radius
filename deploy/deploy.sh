#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-${DOMAIN:-}}"
REPOSITORY="${2:-${REPOSITORY:-https://github.com/Lockelamoree/Blast_Radius.git}}"
BRANCH="${BLAST_RADIUS_BRANCH:-main}"
LIVE_GENERATION_VALUE="${BLAST_RADIUS_LIVE_GENERATION:-false}"
APP_DIR="/opt/blast-radius"
RELEASES_DIR="/opt/blast-radius-releases"
STATE_DIR="/var/lib/blast-radius"
ENV_FILE="/etc/blast-radius.env"
RUNTIME_USER="blast-radius"

# Capture a caller-supplied key before any package manager, Git, or build child is started.
# Keep the value in a non-exported shell variable and expose it only to update_env.py.
OPENAI_KEY_SUPPLIED=0
OPENAI_KEY_VALUE=""
if [[ -v OPENAI_API_KEY ]]; then
  OPENAI_KEY_SUPPLIED=1
  OPENAI_KEY_VALUE="$OPENAI_API_KEY"
fi
unset OPENAI_API_KEY

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/deploy.sh your-domain.example" >&2
  exit 1
fi

if [[ "${BLAST_RADIUS_PROMPT_FOR_OPENAI_KEY:-0}" == "1" && "$OPENAI_KEY_SUPPLIED" == "0" ]]; then
  if [[ ! -r /dev/tty ]]; then
    echo "Cannot prompt for OPENAI_API_KEY without an interactive terminal." >&2
    exit 1
  fi
  read -r -s -p "Spend-capped OpenAI API key: " OPENAI_KEY_VALUE </dev/tty
  printf '\n' >/dev/tty
  OPENAI_KEY_SUPPLIED=1
fi

if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || [[ "$DOMAIN" != *.* ]]; then
  echo "A valid public DNS hostname is required." >&2
  exit 1
fi
if [[ ! "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]]; then
  echo "BLAST_RADIUS_BRANCH contains unsupported characters." >&2
  exit 1
fi
if [[ "$LIVE_GENERATION_VALUE" != "true" && "$LIVE_GENERATION_VALUE" != "false" ]]; then
  echo "BLAST_RADIUS_LIVE_GENERATION must be true or false." >&2
  exit 1
fi

if ! command -v flock >/dev/null 2>&1; then
  echo "The standard flock utility is required (install util-linux)." >&2
  exit 1
fi
exec 9>/var/lock/blast-radius-deploy.lock
if ! flock -n 9; then
  echo "Another Blast Radius deployment is already running." >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl debian-keyring debian-archive-keyring git gnupg python3 python3-pip python3-venv

if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  echo "Blast Radius requires Python 3.11+. Use Ubuntu 24.04 LTS or install a supported Python first." >&2
  exit 1
fi

if ! command -v caddy >/dev/null 2>&1; then
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

if ! id "$RUNTIME_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$RUNTIME_USER"
fi
install -d -m 755 -o root -g root "$RELEASES_DIR"
install -d -m 750 -o "$RUNTIME_USER" -g "$RUNTIME_USER" "$STATE_DIR"

INCOMING_DIR="$(mktemp -d "$RELEASES_DIR/.incoming.XXXXXX")"
CADDY_CANDIDATE="$(mktemp)"
ENV_CANDIDATE="$(mktemp)"
HEALTH_ERROR_FILE="$(mktemp)"
ROLLBACK_DIR="$(mktemp -d)"
chmod 700 "$ROLLBACK_DIR"
NEXT_LINK="${APP_DIR}.next.$$"
CUTOVER_STARTED=0
DEPLOY_SUCCESS=0
PREVIOUS_KIND="none"
PREVIOUS_TARGET=""
PREVIOUS_REVISION=""
RELEASE_DIR=""
LEGACY_MUTATED=0

backup_file() {
  local source="$1"
  local name="$2"
  if [[ -f "$source" ]]; then
    cp -a "$source" "$ROLLBACK_DIR/$name"
  else
    touch "$ROLLBACK_DIR/$name.missing"
  fi
}

restore_file() {
  local destination="$1"
  local name="$2"
  if [[ -f "$ROLLBACK_DIR/$name" ]]; then
    cp -a "$ROLLBACK_DIR/$name" "$destination"
  else
    rm -f -- "$destination"
  fi
}

cleanup() {
  local status=$?
  local rollback_failed=0
  local keep_rollback=0
  local restored_health=""
  local restored_ready=0
  local candidate=""
  local candidate_name=""
  trap - EXIT
  set +e
  OPENAI_KEY_VALUE=""
  if [[ "$status" != "0" && "$DEPLOY_SUCCESS" != "1" && "$CUTOVER_STARTED" == "1" ]]; then
    if [[ "$PREVIOUS_KIND" == "secure" || "$PREVIOUS_KIND" == "none" ]]; then
      printf 'Deployment failed; restoring the previous trusted configuration.\n' >&2
      systemctl stop blast-radius.service >/dev/null 2>&1 || true
      rm -f -- "$NEXT_LINK" || rollback_failed=1
      if [[ "$PREVIOUS_KIND" == "secure" ]]; then
        ln -s "$PREVIOUS_TARGET" "$NEXT_LINK" || rollback_failed=1
        mv -Tf "$NEXT_LINK" "$APP_DIR" || rollback_failed=1
      else
        rm -f -- "$APP_DIR" || rollback_failed=1
      fi
      restore_file "$ENV_FILE" env || rollback_failed=1
      restore_file /etc/systemd/system/blast-radius.service unit || rollback_failed=1
      restore_file /etc/caddy/Caddyfile caddy || rollback_failed=1
      systemctl daemon-reload >/dev/null 2>&1 || rollback_failed=1
      if [[ "$PREVIOUS_KIND" == "secure" ]]; then
        systemctl restart blast-radius.service >/dev/null 2>&1 || rollback_failed=1
        for _ in $(seq 1 10); do
          if restored_health="$(curl --connect-timeout 2 --max-time 4 -fsS http://127.0.0.1:8000/healthz 2>/dev/null)" && \
             python3 -c 'import json,sys; h=json.load(sys.stdin); raise SystemExit(0 if h.get("status") == "ok" and h.get("revision") == sys.argv[1] else 1)' \
               "$PREVIOUS_REVISION" <<< "$restored_health"; then
            restored_ready=1
            break
          fi
          sleep 1
        done
        if [[ "$restored_ready" != "1" ]]; then
          rollback_failed=1
        fi
      fi
      systemctl reload caddy.service >/dev/null 2>&1 || rollback_failed=1
      if [[ "$rollback_failed" == "1" ]]; then
        keep_rollback=1
        status=70
        printf 'ROLLBACK FAILED; manual recovery files remain at %s.\n' "$ROLLBACK_DIR" >&2
        journalctl -u blast-radius.service -n 80 --no-pager >&2 || true
        journalctl -u caddy.service -n 80 --no-pager >&2 || true
      else
        printf 'Previous trusted deployment restored and verified.\n' >&2
      fi
    elif [[ "$PREVIOUS_KIND" == "legacy" && "$LEGACY_MUTATED" == "0" ]]; then
      printf 'Deployment stopped before legacy state changed; restarting the unchanged service.\n' >&2
      if ! systemctl restart blast-radius.service >/dev/null 2>&1; then
        rollback_failed=1
      fi
      for _ in $(seq 1 10); do
        if restored_health="$(curl --connect-timeout 2 --max-time 4 -fsS http://127.0.0.1:8000/healthz 2>/dev/null)" && \
           python3 -c 'import json,sys; h=json.load(sys.stdin); raise SystemExit(0 if h.get("status") == "ok" else 1)' <<< "$restored_health"; then
          restored_ready=1
          break
        fi
        sleep 1
      done
      if [[ "$restored_ready" != "1" ]]; then
        rollback_failed=1
      fi
      if [[ "$rollback_failed" == "1" ]]; then
        keep_rollback=1
        status=70
        printf 'ROLLBACK FAILED; the unchanged legacy service did not recover.\n' >&2
        journalctl -u blast-radius.service -n 80 --no-pager >&2 || true
      else
        printf 'Unchanged legacy service restarted and verified.\n' >&2
      fi
    else
      keep_rollback=1
      printf 'Deployment failed after quarantining a legacy writable checkout; no unsafe rollback was activated.\n' >&2
      printf 'Manual recovery files remain at %s.\n' "$ROLLBACK_DIR" >&2
    fi
  fi
  rm -f -- "$CADDY_CANDIDATE" "$ENV_CANDIDATE" "$HEALTH_ERROR_FILE" "$NEXT_LINK"
  if [[ "$status" != "0" && "$rollback_failed" == "0" && \
        -n "$RELEASE_DIR" && "$RELEASE_DIR" == "$RELEASES_DIR/"* && \
        -d "$RELEASE_DIR" && "$(readlink -f "$APP_DIR" 2>/dev/null)" != "$RELEASE_DIR" ]]; then
    rm -rf -- "$RELEASE_DIR"
  fi
  if [[ "$status" == "0" && "$DEPLOY_SUCCESS" == "1" ]]; then
    for candidate in "$RELEASES_DIR"/*; do
      [[ -d "$candidate" ]] || continue
      candidate_name="${candidate##*/}"
      [[ "$candidate_name" =~ ^[0-9a-f]{40,64}-[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || continue
      [[ "$candidate" == "$RELEASE_DIR" || "$candidate" == "$PREVIOUS_TARGET" ]] && continue
      rm -rf -- "$candidate"
    done
  fi
  if [[ "$keep_rollback" != "1" ]]; then
    rm -rf -- "$ROLLBACK_DIR"
  fi
  if [[ -n "${INCOMING_DIR:-}" && "$INCOMING_DIR" == "$RELEASES_DIR/.incoming."* ]]; then
    rm -rf -- "$INCOMING_DIR"
  fi
  exit "$status"
}
trap cleanup EXIT

git clone --branch "$BRANCH" --single-branch -- "$REPOSITORY" "$INCOMING_DIR"
if [[ "$(git -C "$INCOMING_DIR" remote get-url origin)" != "$REPOSITORY" ]]; then
  echo "Cloned origin does not match the requested repository." >&2
  exit 1
fi
if [[ "$(git -C "$INCOMING_DIR" branch --show-current)" != "$BRANCH" ]]; then
  echo "Cloned checkout is not on the requested branch." >&2
  exit 1
fi
DEPLOY_REVISION="$(git -C "$INCOMING_DIR" rev-parse HEAD)"
REMOTE_REVISION="$(git -C "$INCOMING_DIR" rev-parse "refs/remotes/origin/$BRANCH")"
if [[ "$DEPLOY_REVISION" != "$REMOTE_REVISION" ]]; then
  echo "Cloned revision does not match origin/$BRANCH." >&2
  exit 1
fi
if [[ -n "$(git -C "$INCOMING_DIR" status --porcelain --untracked-files=all)" ]]; then
  echo "Fresh release checkout is unexpectedly dirty." >&2
  exit 1
fi

RELEASE_DIR="$RELEASES_DIR/${DEPLOY_REVISION}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mv "$INCOMING_DIR" "$RELEASE_DIR"
INCOMING_DIR=""
python3 -m venv "$RELEASE_DIR/.venv"
"$RELEASE_DIR/.venv/bin/python" -m pip install --upgrade pip
"$RELEASE_DIR/.venv/bin/python" -m pip install "$RELEASE_DIR"
chown -R root:root "$RELEASE_DIR"
chmod -R u=rwX,go=rX "$RELEASE_DIR"
runuser -u "$RUNTIME_USER" -- "$RELEASE_DIR/.venv/bin/python" -I -c \
  "from blast_radius.config import Settings; from blast_radius.engine.bank import ScenarioBank; assert len(ScenarioBank(Settings().data_dir).scenarios) == 18"

sed "s/blast-radius\.example\.com/$DOMAIN/g" "$RELEASE_DIR/deploy/Caddyfile" > "$CADDY_CANDIDATE"
caddy validate --config "$CADDY_CANDIDATE" --adapter caddyfile

if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "$ENV_CANDIDATE"
fi
chmod 600 "$ENV_CANDIDATE"
ENV_BUDGET="${BLAST_RADIUS_DAILY_LLM_BUDGET:-500}"
if [[ "$OPENAI_KEY_SUPPLIED" == "1" ]]; then
  BLAST_RADIUS_UPDATE_OPENAI_KEY=1 \
  OPENAI_API_KEY="$OPENAI_KEY_VALUE" \
  BLAST_RADIUS_DAILY_LLM_BUDGET="$ENV_BUDGET" \
  BLAST_RADIUS_LIVE_GENERATION="$LIVE_GENERATION_VALUE" \
  BLAST_RADIUS_REVISION="$DEPLOY_REVISION" \
    python3 "$RELEASE_DIR/deploy/update_env.py" "$ENV_CANDIDATE" "$STATE_DIR"
else
  BLAST_RADIUS_UPDATE_OPENAI_KEY=0 \
  BLAST_RADIUS_DAILY_LLM_BUDGET="$ENV_BUDGET" \
  BLAST_RADIUS_LIVE_GENERATION="$LIVE_GENERATION_VALUE" \
  BLAST_RADIUS_REVISION="$DEPLOY_REVISION" \
    python3 "$RELEASE_DIR/deploy/update_env.py" "$ENV_CANDIDATE" "$STATE_DIR"
fi
OPENAI_KEY_VALUE=""

if [[ -L "$APP_DIR" ]]; then
  PREVIOUS_TARGET="$(readlink -f "$APP_DIR")"
  if [[ "$PREVIOUS_TARGET" != "$RELEASES_DIR/"* || ! -d "$PREVIOUS_TARGET" ]]; then
    echo "Existing application symlink does not target a trusted release." >&2
    exit 1
  fi
  if [[ "$(stat -c %u "$PREVIOUS_TARGET")" != "0" ]] || \
     [[ -n "$(find "$PREVIOUS_TARGET" -xdev \( -type f -o -type d \) -perm /022 -print -quit)" ]]; then
    echo "Existing release is not root-owned and immutable; refusing unsafe rollback." >&2
    exit 1
  fi
  PREVIOUS_REVISION="$(git -C "$PREVIOUS_TARGET" rev-parse HEAD)"
  PREVIOUS_KIND="secure"
elif [[ -d "$APP_DIR" ]]; then
  PREVIOUS_KIND="legacy"
elif [[ -e "$APP_DIR" ]]; then
  echo "$APP_DIR exists but is not a deployable directory or symlink." >&2
  exit 1
fi

backup_file "$ENV_FILE" env
backup_file /etc/systemd/system/blast-radius.service unit
backup_file /etc/caddy/Caddyfile caddy
CUTOVER_STARTED=1

if systemctl cat blast-radius.service >/dev/null 2>&1; then
  systemctl stop blast-radius.service
  if systemctl is-active --quiet blast-radius.service; then
    echo "Existing Blast Radius service did not stop; refusing to overlap releases." >&2
    exit 1
  fi
fi

# Migrate the database once from the legacy writable checkout, then quarantine that
# checkout as root-owned data. New releases are immutable and state lives under /var/lib.
if [[ -d "$APP_DIR" && ! -L "$APP_DIR" ]]; then
  LEGACY_DIR="$RELEASES_DIR/legacy-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$APP_DIR" "$LEGACY_DIR"
  LEGACY_MUTATED=1
  if [[ ! -f "$STATE_DIR/blast_radius.db" && -f "$LEGACY_DIR/blast_radius.db" && ! -L "$LEGACY_DIR/blast_radius.db" ]]; then
    runuser -u "$RUNTIME_USER" -- python3 - \
      "$LEGACY_DIR/blast_radius.db" "$STATE_DIR/blast_radius.db" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as source, sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
PY
    chmod 600 "$STATE_DIR/blast_radius.db"
    chown "$RUNTIME_USER:$RUNTIME_USER" "$STATE_DIR/blast_radius.db"
  elif [[ -L "$LEGACY_DIR/blast_radius.db" ]]; then
    echo "Skipping unsafe symlinked legacy database; the new state store will initialize cleanly." >&2
  fi
  chown -R root:root "$LEGACY_DIR"
  chmod -R go-w "$LEGACY_DIR"
elif [[ -e "$APP_DIR" && ! -L "$APP_DIR" ]]; then
  echo "$APP_DIR exists but is not a deployable directory or symlink." >&2
  exit 1
fi

ln -s "$RELEASE_DIR" "$NEXT_LINK"
mv -Tf "$NEXT_LINK" "$APP_DIR"

install -m 600 -o root -g root "$ENV_CANDIDATE" "$ENV_FILE"
install -m 644 "$RELEASE_DIR/deploy/blast-radius.service" /etc/systemd/system/blast-radius.service
install -m 644 "$CADDY_CANDIDATE" /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable blast-radius.service
systemctl restart blast-radius.service
systemctl enable caddy.service
systemctl reload-or-restart caddy.service

LOCAL_HEALTH_JSON=""
LOCAL_HEALTH_VALID=0
for _ in $(seq 1 20); do
  if ! LOCAL_HEALTH_JSON="$(curl --connect-timeout 2 --max-time 5 -fsS http://127.0.0.1:8000/healthz 2>"$HEALTH_ERROR_FILE")"; then
    sleep 1
    continue
  fi
  if python3 -c 'import json,sys; h=json.load(sys.stdin); expected=(sys.argv[2] == "true"); ok=(h.get("status") == "ok" and h.get("revision") == sys.argv[1] and h.get("bank_scenarios") == 18 and h.get("live_generation") is expected and h.get("critic_model") == "gpt-5.6-sol"); raise SystemExit(0 if ok else 1)' \
       "$DEPLOY_REVISION" "$LIVE_GENERATION_VALUE" <<< "$LOCAL_HEALTH_JSON"; then
    LOCAL_HEALTH_VALID=1
    break
  fi
  sleep 1
done
if [[ "$LOCAL_HEALTH_VALID" != "1" ]]; then
  printf 'ERROR: the new local Uvicorn process did not report the expected release invariants.\n' >&2
  cat "$HEALTH_ERROR_FILE" >&2 || true
  journalctl -u blast-radius.service -n 80 --no-pager >&2 || true
  exit 1
fi

HEALTH_JSON=""
HEALTH_STATUS="missing"
GRADING_STATE="key_present_unverified"
GENERATION_STATE="true"
HEALTH_REVISION="unknown"
BANK_SCENARIOS="0"
HEALTH_CRITIC_MODEL="missing"
for _ in $(seq 1 20); do
  : > "$HEALTH_ERROR_FILE"
  if ! HEALTH_JSON="$(curl --connect-timeout 5 --max-time 12 -fsS "https://$DOMAIN/healthz" 2>"$HEALTH_ERROR_FILE")"; then
    sleep 2
    continue
  fi
  if ! HEALTH_FIELDS="$(python3 -c 'import json,sys; h=json.load(sys.stdin); print(h["status"], h["reasoning_grading"], str(h["live_generation"]).lower(), h["revision"], h["bank_scenarios"], h["critic_model"])' <<< "$HEALTH_JSON" 2>/dev/null)"; then
    sleep 2
    continue
  fi
  read -r HEALTH_STATUS GRADING_STATE GENERATION_STATE HEALTH_REVISION BANK_SCENARIOS HEALTH_CRITIC_MODEL <<< "$HEALTH_FIELDS"
  if [[ "$HEALTH_STATUS" == "ok" && "$GRADING_STATE" != "key_present_unverified" ]]; then
    break
  fi
  sleep 2
done
if [[ -z "$HEALTH_JSON" ]]; then
  printf 'ERROR: deployment health endpoint did not become reachable.\n' >&2
  cat "$HEALTH_ERROR_FILE" >&2 || true
  journalctl -u blast-radius.service -n 80 --no-pager >&2 || true
  exit 1
fi
printf '%s\n' "$HEALTH_JSON"
printf 'Reasoning grading state: %s\n' "$GRADING_STATE"
printf 'Deployment revision: %s\n' "$HEALTH_REVISION"
if [[ "$HEALTH_STATUS" != "ok" ]]; then
  printf 'ERROR: health status is %s, expected ok.\n' "$HEALTH_STATUS" >&2
  exit 1
fi
if [[ "$HEALTH_CRITIC_MODEL" != "gpt-5.6-sol" ]]; then
  printf 'ERROR: health reports critic model %s, expected gpt-5.6-sol.\n' "$HEALTH_CRITIC_MODEL" >&2
  exit 1
fi
if [[ "$HEALTH_REVISION" != "$DEPLOY_REVISION" ]]; then
  printf 'ERROR: health revision %s does not match deployed revision %s.\n' "$HEALTH_REVISION" "$DEPLOY_REVISION" >&2
  exit 1
fi
if [[ "$BANK_SCENARIOS" != "18" ]]; then
  printf 'ERROR: expected 18 verified scenarios, health reports %s.\n' "$BANK_SCENARIOS" >&2
  exit 1
fi
if [[ "$GENERATION_STATE" != "$LIVE_GENERATION_VALUE" ]]; then
  printf 'ERROR: health reports live_generation=%s, expected %s.\n' "$GENERATION_STATE" "$LIVE_GENERATION_VALUE" >&2
  exit 1
fi
if [[ "$GRADING_STATE" != "live" ]]; then
  printf 'ERROR: GPT reasoning grading is not verified; recent service logs follow.\n' >&2
  journalctl -u blast-radius.service -n 80 --no-pager >&2 || true
  if [[ "${BLAST_RADIUS_ALLOW_DEGRADED_DEPLOY:-0}" != "1" ]]; then
    printf 'Set BLAST_RADIUS_ALLOW_DEGRADED_DEPLOY=1 only for an intentional fallback-only deploy.\n' >&2
    exit 1
  fi
  printf 'WARNING: continuing with deterministic grading by explicit override.\n' >&2
fi
DEPLOY_SUCCESS=1
printf 'Blast Radius is healthy at https://%s\n' "$DOMAIN"
