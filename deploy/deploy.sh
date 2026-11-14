#!/usr/bin/env bash
# Push this laptop's Plumbline to the Vultr server and restart it. Run from the repo root:
#   deploy/deploy.sh <server-ip> [--setup SITE [SITE_PASSWORD]]
# --setup runs the one-time server setup (packages, firewall, service, HTTPS) after the first copy.
# Keys (backend/.env), the CoStar data and the Solana wallet are copied over SSH; they never go into git.
set -euo pipefail
IP="${1:?usage: deploy/deploy.sh <server-ip> [--setup SITE [SITE_PASSWORD]]}"
KEY="${PLUMBLINE_SSH_KEY:-$HOME/.ssh/plumbline_vultr}"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new root@$IP"
RSYNC="rsync -az --delete -e \"ssh -i $KEY -o StrictHostKeyChecking=accept-new\""
cd "$(dirname "$0")/.."

echo "== Building the frontend"
(cd frontend && npx vite build >/dev/null)

echo "== Copying the app"
$SSH "mkdir -p /opt/plumbline"
eval $RSYNC \
  --exclude .git --exclude node_modules --exclude .venv --exclude __pycache__ --exclude .pytest_cache \
  --exclude .claude --exclude .DS_Store --exclude '*.zip' \
  --exclude backend/app/data/agent_memory.json --exclude backend/app/data/solana \
  --exclude backend/app/data/models_index.csv --exclude backend/app/data/AGENTS.md \
  ./ "root@$IP:/opt/plumbline/"
# First deploy only: the agent's memory and the Solana wallet start as this laptop's copies, then live on the server.
eval rsync -az --ignore-existing -e \"ssh -i $KEY\" backend/app/data/solana "root@$IP:/opt/plumbline/backend/app/data/" || true
[ -f backend/app/data/agent_memory.json ] && eval rsync -az --ignore-existing -e \"ssh -i $KEY\" backend/app/data/agent_memory.json "root@$IP:/opt/plumbline/backend/app/data/" || true

if [ "${2:-}" = "--setup" ]; then
  echo "== One-time server setup"
  $SSH "SITE='${3:?site}' SITE_PASSWORD='${4:-}' bash /opt/plumbline/deploy/server_setup.sh"
fi

echo "== Installing Python packages and restarting"
$SSH "set -e; cd /opt/plumbline/backend
  [ -d .venv ] || python3.12 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  chown -R plumbline:plumbline /opt/plumbline
  chmod 600 /opt/plumbline/backend/.env 2>/dev/null || true
  chmod -R go-rwx /opt/plumbline/backend/app/data/solana /opt/plumbline/backend/app/data/real 2>/dev/null || true
  systemctl restart plumbline
  for i in \$(seq 1 30); do curl -sf http://127.0.0.1:8787/api/health >/dev/null && break; sleep 1; done
  curl -sf http://127.0.0.1:8787/api/health && echo && systemctl is-active plumbline"
echo "== Deployed"
