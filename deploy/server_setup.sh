#!/usr/bin/env bash
# One-time setup of a fresh Vultr Ubuntu 24.04 server for Plumbline. Run as root on the server:
#   SITE=plumbline.us PUBLIC_URL=https://plumbline.us SITE_PASSWORD=... bash server_setup.sh
# SITE is the hostname Caddy serves with automatic HTTPS (a domain, or <ip-with-dashes>.sslip.io).
# SITE_PASSWORD is optional: when set, the whole site asks for user "plumbline" and this password.
set -euo pipefail
: "${SITE:?set SITE}"
PUBLIC_URL="${PUBLIC_URL:-https://$SITE}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3.12 python3.12-venv python3-pip caddy rsync ufw

# Firewall: SSH and web only. The app itself listens on localhost; Caddy is the only door in.
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

id plumbline >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/plumbline --shell /usr/sbin/nologin plumbline
mkdir -p /opt/plumbline
chown -R plumbline:plumbline /opt/plumbline

# Server-only settings. systemd passes them to the app; they win over backend/.env.
cat > /etc/plumbline.env <<EOF
PUBLIC_URL=$PUBLIC_URL
PLUMBLINE_HOST=vultr
EOF
chmod 600 /etc/plumbline.env

cp /opt/plumbline/deploy/plumbline.service /etc/systemd/system/plumbline.service
systemctl daemon-reload
systemctl enable plumbline

# Caddy: automatic HTTPS, optional password, and no buffering so live updates (server-sent events) stream.
AUTH=""
if [ -n "${SITE_PASSWORD:-}" ]; then
  HASH=$(caddy hash-password --plaintext "$SITE_PASSWORD")
  AUTH="basicauth * {
    plumbline $HASH
  }"
fi
cat > /etc/caddy/Caddyfile <<EOF
$SITE {
  $AUTH
  reverse_proxy 127.0.0.1:8787 {
    flush_interval -1
  }
  header {
    Strict-Transport-Security "max-age=31536000"
    X-Content-Type-Options nosniff
    Referrer-Policy strict-origin-when-cross-origin
  }
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
systemctl reload caddy || systemctl restart caddy
echo "Server ready for $SITE"
