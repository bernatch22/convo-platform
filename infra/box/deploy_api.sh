#!/usr/bin/env bash
# deploy_api.sh — put the control plane + public console on convo-box, from the laptop.
#
#   ./infra/box/deploy_api.sh
#
# Idempotent: updates the repo, builds the UI, installs api.py under systemd sharing
# the worker's WorkingDirectory (so one tmp/convo.db serves both), ships the Caddyfile,
# opens 80/443, brings Caddy up, and sets LIVEKIT_PUBLIC_URL so browser tokens point
# at the public host while the worker keeps using loopback.
set -euo pipefail
BOX="${BOX:-convo-box}"
APP=/home/berna/convo-app
HERE="$(cd "$(dirname "$0")" && pwd)"
DOMAIN=lk.bernardocastro.dev

echo "── repo + deps + UI build"
ssh "$BOX" "cd $APP && git fetch -q origin && git reset -q --hard origin/master && ~/.local/bin/uv sync -q --extra dev"
ssh "$BOX" "command -v node >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq nodejs npm; }"
ssh "$BOX" "cd $APP/ui && npm ci --silent && npm run build >/dev/null && echo 'ui built'"

echo "── LIVEKIT_PUBLIC_URL in the box env (browser tokens point at the public host)"
ssh "$BOX" "cd $APP && grep -q '^LIVEKIT_PUBLIC_URL=' .env || echo 'LIVEKIT_PUBLIC_URL=wss://$DOMAIN' >> .env && chmod 600 .env"

echo "── firewall for 80/443 (Caddy ACME + TLS)"
gcloud compute firewall-rules describe convo-web --project hiding-place-447317-c6 >/dev/null 2>&1 && \
  gcloud compute firewall-rules update convo-web --project hiding-place-447317-c6 --allow tcp:80,tcp:443,tcp:7880,tcp:7881 >/dev/null 2>&1 || true

echo "── Caddy config + up"
scp -q "$HERE/Caddyfile" "$HERE/../compose/box.yml" "$BOX:/home/berna/convo/"
ssh "$BOX" "cd /home/berna/convo && sudo docker compose -f box.yml up -d caddy 2>&1 | tail -2"

echo "── api.py under systemd"
scp -q "$HERE/convo-api.service" "$BOX:/tmp/convo-api.service"
ssh "$BOX" 'sudo mv /tmp/convo-api.service /etc/systemd/system/convo-api.service && sudo systemctl daemon-reload && sudo systemctl enable -q convo-api && sudo systemctl restart convo-api'
sleep 6
ssh "$BOX" 'systemctl is-active convo-api convo-worker; sudo docker ps --format "{{.Names}} {{.Status}}" | grep caddy'

echo "── health from the internet"
sleep 4
curl -s -o /dev/null -w "   https://$DOMAIN → %{http_code}\n" "https://$DOMAIN/" || true
curl -s "https://$DOMAIN/tenants" -o /dev/null -w "   /tenants → %{http_code}\n" || true

echo "── nightly ring-2 evals (timer, 04:00 Europe/Madrid)"
scp -q "$HERE/convo-evals.service" "$HERE/convo-evals.timer" "$BOX:/tmp/"
ssh "$BOX" 'sudo mv /tmp/convo-evals.service /tmp/convo-evals.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable -q --now convo-evals.timer'
ssh "$BOX" 'systemctl list-timers convo-evals.timer --no-pager | head -3'
echo "   one night by hand:  ssh $BOX 'sudo systemctl start convo-evals.service'"
echo "   what it would spend: ssh $BOX 'cd $APP && ~/.local/bin/uv run python -m convo evals nightly --dry-run'"
