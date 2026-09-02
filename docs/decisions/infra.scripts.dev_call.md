# `infra.scripts.dev_call`

The reasoning that used to live in the docstrings of `infra/scripts/dev_call.py`; the code keeps one line per symbol.

## module

The stack runs in three terminals (compose up · `uvicorn api:app` ·
`python worker.py dev`); this script is the fourth, standing in for the web
client nobody has written yet. It asks the control plane for a token, joins the
room that token names, types on `lk.chat`, reads the agent's deltas on
`lk.transcription` and hangs up.

    uv run python scripts/dev_call.py                          # both demo tenants
    uv run python scripts/dev_call.py clinica-norte/reagendamiento
    uv run python scripts/dev_call.py tienda-sur/pedidos "hola" "¿cuándo llega?"

Nothing below knows a tenant. Who answers is decided by the dispatch metadata
inside the token — `RoomAgentDispatch(agent_name=FLEET, metadata=SessionMeta)`
— which is exactly what this run exists to prove: one worker process, two
businesses, no `TENANT` in its environment.

Open source note: this is a generic LiveKit text-mode client in 150 lines. Point
`--api` at any control plane that mints `{url, room, token}` and it works.

## ChatCall.reply

A turn that calls a tool speaks twice — "un momento, le consulto" and
then the answer — so waiting for one segment and moving on would type
the next line over the agent's mouth.
