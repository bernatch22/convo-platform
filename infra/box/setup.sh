#!/usr/bin/env bash
# setup.sh — stand convo-box up, idempotently, from the laptop.
#
#   ./infra/box/setup.sh            # install docker, render configs, compose up
#
# The API keypair is GENERATED ON THE BOX on first run and never leaves it
# except into the local .env (chmod 600, gitignored) so the worker can sign
# tokens. Re-running is a no-op: keys are kept, containers restart only if
# their config changed.
set -euo pipefail
BOX="${BOX:-convo-box}"
DIR="/home/berna/convo"
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/../../.env}"

echo "── docker present?"
ssh "$BOX" 'command -v docker >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq docker.io docker-compose-v2; }'

echo "── keypair (generated once, kept forever)"
ssh "$BOX" "mkdir -p $DIR && cd $DIR && if [ ! -f livekit.env ]; then umask 077; printf 'LIVEKIT_API_KEY=API%s\nLIVEKIT_API_SECRET=%s\n' \"\$(openssl rand -hex 6)\" \"\$(openssl rand -hex 32)\" > livekit.env; fi"

echo "── ship configs"
scp -q "$HERE/livekit.tpl.yml" "$HERE/sip.tpl.yml" "$HERE/../compose/box.yml" "$BOX:$DIR/"
ssh "$BOX" "cd $DIR && set -a && . ./livekit.env && set +a && umask 077 && sed -e \"s|__API_KEY__|\$LIVEKIT_API_KEY|\" -e \"s|__API_SECRET__|\$LIVEKIT_API_SECRET|\" livekit.tpl.yml > livekit.yml && sed -e \"s|__API_KEY__|\$LIVEKIT_API_KEY|\" -e \"s|__API_SECRET__|\$LIVEKIT_API_SECRET|\" sip.tpl.yml > sip.yml"

echo "── compose up"
ssh "$BOX" "cd $DIR && sudo docker compose -f box.yml up -d --quiet-pull 2>&1 | tail -3"

echo "── mirror keys into $ENV_FILE (worker signs tokens with them)"
KEY=$(ssh "$BOX" "sed -n 's/^LIVEKIT_API_KEY=//p' $DIR/livekit.env")
SECRET=$(ssh "$BOX" "sed -n 's/^LIVEKIT_API_SECRET=//p' $DIR/livekit.env")
touch "$ENV_FILE" && chmod 600 "$ENV_FILE"
python3 - "$ENV_FILE" "$KEY" "$SECRET" <<'PY'
import sys
path, key, secret = sys.argv[1:4]
lines = [l for l in open(path).read().splitlines()
         if not l.startswith(("LIVEKIT_URL=", "LIVEKIT_API_KEY=", "LIVEKIT_API_SECRET="))]
lines += [f"LIVEKIT_URL=ws://lk.bernardocastro.dev:7880",
          f"LIVEKIT_API_KEY={key}", f"LIVEKIT_API_SECRET={secret}"]
open(path, "w").write("\n".join(lines) + "\n")
print(f"updated {path} (url + keypair, values not shown)")
PY

echo "── health"
ssh "$BOX" "sudo docker ps --format '{{.Names}} {{.Status}}' | sed 's/^/   /'"
curl -s -o /dev/null -w "   livekit from the internet: HTTP %{http_code}\n" http://lk.bernardocastro.dev:7880
