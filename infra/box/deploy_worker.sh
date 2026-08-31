#!/usr/bin/env bash
# deploy_worker.sh — put the worker on convo-box, idempotently, from the laptop.
#
#   ./infra/box/deploy_worker.sh
#
# Clones/updates the public repo, syncs deps with uv, ships the laptop's .env
# with LIVEKIT_* rewritten to the box-local SFU (the box's own keypair), adds
# the phone route to the box's store, installs the systemd unit and restarts.
set -euo pipefail
BOX="${BOX:-convo-box}"
APP=/home/berna/convo-app
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "── uv + repo"
ssh "$BOX" 'command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh -s -- -q'
ssh "$BOX" "if [ -d $APP/.git ]; then git -C $APP fetch -q origin && git -C $APP reset -q --hard origin/master; else git clone -q https://github.com/bernatch22/convo-platform.git $APP; fi"
# `--extra dev` even though the worker needs none of it: both services share ONE venv
# and `uv sync` makes that venv match its arguments EXACTLY, so a bare sync here uninstalls
# what deploy_api.sh installed. The control plane's scoring path imports deepeval
# (core/scoring/runner.py → core.testing.replay), so a worker deploy that ran second left
# every finished call unscored with `ModuleNotFoundError: No module named 'deepeval'` in
# the api's log and nothing at all in the console. Found 2026-09-01, after a call showed
# no score. The two scripts must ask for the same environment or the second one wins.
ssh "$BOX" "cd $APP && ~/.local/bin/uv sync -q --extra dev"

echo "── env (provider keys from the laptop; LIVEKIT_* rewritten to the box's own)"
scp -q "$HERE/../../.env" "$BOX:$APP/.env"
ssh "$BOX" "cd $APP && chmod 600 .env && set -a && . /home/berna/convo/livekit.env && set +a && python3 - <<'PY'
import os
lines = [l for l in open('.env').read().splitlines()
         if not l.startswith(('LIVEKIT_URL=', 'LIVEKIT_PUBLIC_URL=', 'LIVEKIT_API_KEY=',
                              'LIVEKIT_API_SECRET=', 'TENANT=', 'PROJECT='))]
lines += ['LIVEKIT_URL=ws://127.0.0.1:7880',
          'LIVEKIT_API_KEY=' + os.environ['LIVEKIT_API_KEY'],
          'LIVEKIT_API_SECRET=' + os.environ['LIVEKIT_API_SECRET'],
          # The laptop's .env has no PUBLIC url — it has no public host — so copying it
          # over the box's DELETES this line, and every ticket the control plane mints
          # then carries the loopback the WORKER uses. A browser handed that connects to
          # its own machine: 'invalid API key', with the box's key in the message, from a
          # server that never signed it. It is written here, next to the two keys, because
          # this is the script that overwrites the file.
          'LIVEKIT_PUBLIC_URL=wss://lk.bernardocastro.dev']
open('.env', 'w').write('\n'.join(lines) + '\n')
print('env written (values not shown)')
PY"

echo "── the phone route, on the box's own store"
ssh "$BOX" "cd $APP && ~/.local/bin/uv run python -m convo routes add cc +14176743169 clinica-norte reagendamiento voice && ~/.local/bin/uv run python -m convo routes list"

echo "── systemd"
scp -q "$HERE/convo-worker.service" "$BOX:/tmp/convo-worker.service"
ssh "$BOX" 'sudo mv /tmp/convo-worker.service /etc/systemd/system/convo-worker.service && sudo systemctl daemon-reload && sudo systemctl enable -q convo-worker && sudo systemctl restart convo-worker'
sleep 6
ssh "$BOX" 'systemctl is-active convo-worker && journalctl -u convo-worker -n 4 --no-pager -o cat | grep -v KEY'
