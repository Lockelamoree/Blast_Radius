#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-${DOMAIN:-}}"
REPOSITORY="${2:-${REPOSITORY:-https://github.com/Lockelamoree/Blast_Radius.git}}"
APP_DIR="/opt/blast-radius"
ENV_FILE="/etc/blast-radius.env"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/deploy.sh your-domain.example" >&2
  exit 1
fi

if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || [[ "$DOMAIN" != *.* ]]; then
  echo "A valid public DNS hostname is required." >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl debian-keyring debian-archive-keyring git gnupg python3 python3-pip python3-venv

if ! command -v caddy >/dev/null 2>&1; then
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

if ! id blast-radius >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin blast-radius
fi

if [[ -d "$APP_DIR/.git" ]]; then
  runuser -u blast-radius -- git -C "$APP_DIR" pull --ff-only
else
  install -d -o blast-radius -g blast-radius "$APP_DIR"
  runuser -u blast-radius -- git clone "$REPOSITORY" "$APP_DIR"
fi

runuser -u blast-radius -- python3 -m venv "$APP_DIR/.venv"
runuser -u blast-radius -- "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
runuser -u blast-radius -- "$APP_DIR/.venv/bin/python" -m pip install -e "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 600 -o root -g root /dev/null "$ENV_FILE"
  {
    printf 'OPENAI_API_KEY=%s\n' "${OPENAI_API_KEY:-}"
    printf 'BLAST_RADIUS_DATABASE=%s\n' "$APP_DIR/blast_radius.db"
    printf 'BLAST_RADIUS_LIVE_GENERATION=false\n'
    printf 'BLAST_RADIUS_SESSION_TTL_MINUTES=180\n'
    printf 'BLAST_RADIUS_DAILY_LLM_BUDGET=%s\n' "${BLAST_RADIUS_DAILY_LLM_BUDGET:-100}"
  } >> "$ENV_FILE"
fi

install -m 644 "$APP_DIR/deploy/blast-radius.service" /etc/systemd/system/blast-radius.service
sed "s/blast-radius\.example\.com/$DOMAIN/g" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile

systemctl daemon-reload
systemctl enable --now blast-radius.service
systemctl enable --now caddy.service
systemctl reload caddy.service

curl --retry 12 --retry-delay 2 --retry-all-errors -fsS "https://$DOMAIN/healthz"
printf '\nBlast Radius is healthy at https://%s\n' "$DOMAIN"
