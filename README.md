# convo-platform

[![ci](https://github.com/bernatch22/convo-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/bernatch22/convo-platform/actions/workflows/ci.yml)

A multi-tenant conversational platform for contact centers — voice and chat —
built on self-hosted [LiveKit](https://livekit.io) (SFU + SIP + Agents),
Anthropic Claude Haiku, Soniox STT and ElevenLabs TTS. One deploy serves many
businesses; the LLM is a swappable interface driver, the platform is a process
runtime that talks.

Built in public as an architecture exercise: the design is in
[`REPORT.md`](REPORT.md), the working rules in [`CLAUDE.md`](CLAUDE.md), and
every step of the build lives on a public taskops board (milestones = chapters,
cards = briefs). Each milestone lands with a learning report under
`.taskops/reports/` — what was achieved, learned and decided.

## Run

```bash
uv sync --extra dev
cp .env.example .env            # keys: Anthropic, Soniox (or Deepgram), ElevenLabs
pytest -m unit                  # fast tests, no keys needed
python worker.py --help         # the LiveKit Agents CLI (console/dev/start)
```

Talk to either demo business in the terminal — one worker, one codebase, two
tenants; what differs is a folder under `tenants/`:

```bash
TENANT=clinica-norte PROJECT=reagendamiento uv run python worker.py console --text
TENANT=tienda-sur    PROJECT=pedidos        uv run python worker.py console --text
```

### Talking to it out loud

Drop `--text` and the console runs in **audio mode**: it opens the laptop
microphone and speaks back through the speakers. The project's STT provider
transcribes (Soniox `stt-rt-v5` by default, Deepgram Flux when the console
switches it — see `core/providers/stt.py`), ElevenLabs
answers in the project's voice, and a local turn detector decides when you have
finished — no LiveKit server, no GPU, nothing to deploy.

```bash
TENANT=clinica-norte PROJECT=reagendamiento uv run python worker.py console
uv run python worker.py console --record          # also leaves the stereo OGG
uv run python worker.py console --list-devices    # pick a microphone
RECORD=1 uv run python worker.py dev              # same recording, against a server
```

While it runs: **Ctrl+T** switches between speaking and typing, **?** lists the
shortcuts, **Ctrl+C** exits.
`--record` writes `console-recordings/session-<stamp>/` — `audio.ogg` (you on
one channel, the agent on the other) and the framework's `session_report.json`.

Interrupting it works, and murmuring at it does not: an interruption needs two
words (`InterruptionOptions.min_words`), and a turn that is nothing but Spanish
backchannel — *vale*, *ajá*, *sí sí*, *mm*, *de acuerdo* — never becomes a
reply. The list is project data (`Project.backchannels`); why there are two
filters instead of one is written in [`core/barge_in.py`](core/barge_in.py).

Then read the call back:

```bash
uv run python -m convo sessions list
uv run python -m convo sessions show <id>
```

The log is append-only and written during the call, so it survives a kill:

```
   5    3767  tts.word     Buenos@0.30 días,@0.11 le@0.21 atiende@0.06 recepción@0.61
   8    5480  stt.final    {"text": "quiero cambiar mi cita", "language": "es"}
   9    5678  turn.user    transcription_delay=0.12s end_of_turn_delay=0.30s {...}
  14   11647  turn.agent   ttft=0.94s e2e=1.87s {"text": "Claro, ¿me dice su DNI?"}
  24   25783  session.end  {"outcome": "completed", "cost": {...}, "audio": "console-recordings/…/audio.ogg"}
```

`stt.final` is the transcript (interim hypotheses are never logged),
`tts.word` the agent's own words with the provider's alignment,
`interruption.false` and `speech.overlap` the barge-in decisions, and the `t_ms`
column is milliseconds since the call started.

### Run against a local server

The console has no server in it. This is the same worker talking to a real
LiveKit SFU, dispatched by the token instead of by `TENANT` — three terminals
and a script:

```bash
# 1 · the SFU and its redis (livekit-server 1.9.1, dev keypair, ports 7880-7882)
docker compose -f infra/compose/dev.yml up

# 2 · the control plane: it mints the JWT that carries the agent dispatch
uv run uvicorn api:app --port 8090

# 3 · the fleet: one worker process, no TENANT and no PROJECT in its environment
env -u TENANT -u PROJECT uv run python worker.py dev
```

Then, in a fourth, the browser-less client — it asks `api.py` for a token,
joins the room that token names, types on `lk.chat` and reads the agent on
`lk.transcription`:

```bash
uv run python scripts/dev_call.py                             # both demo tenants
uv run python scripts/dev_call.py tienda-sur/pedidos          # just one
uv run python scripts/dev_call.py clinica-norte/reagendamiento "hola" "¿y el jueves?"
```

```
── tienda-sur/pedidos · room tienda-sur-pedidos-3128dc53 ──
agent  ▸ Tienda Sur, buenos días. ¿En qué te puedo ayudar?
you    ▸ Buenas, llamo por el pedido TS-10432.
agent  ▸ Perfecto, ahora mismo lo miro. Tengo localizado el pedido TS-10432 de Marta Alonso Gil.
```

Two businesses answered from one process and neither was named in its
environment: who picks up is decided by `RoomAgentDispatch(agent_name=$FLEET,
metadata={tenant, project, channel})`, minted at the door by `api.py` and read
by `core/router.py`. A chat session joins with
`RoomOptions(audio_input=False, audio_output=False)` — text both ways, no
microphone permission asked for.

The calls land in the same log the console writes, and score with the same
metrics:

```bash
uv run python -m convo sessions eval <id>                     # the project's DAGs, ring 3
uv run deepeval test run tests/evals/test_dispatch_ring.py    # the same, as a test
```

`tests/evals/test_dispatch_ring.py` skips itself when no routed session is in
the store: `scripts/dev_call.py` is its fixture, and a suite that failed
because nobody started a server would be reporting on the laptop.

A third business is a copy of [`tenants/_template/`](tenants/_template/README.md),
which walks a stranger through it in ten minutes;
[`docs/tenants.md`](docs/tenants.md) is the table of what a tenant owns and what
the platform owns.

Evals (ring 1, needs `ANTHROPIC_API_KEY`; the judge is Claude Haiku, set
`DEEPEVAL_JUDGE_MODEL` to change it):

```bash
uv run pytest -m unit                     # includes LLM-judged tests when the key is present
uv run deepeval test run tests/evals -n 3 # both tenants' goldens + the cross-tenant leakage pair
```

[`docs/evals.md`](docs/evals.md) explains every metric and how to add one.

## The web UI

`ui/` is the operator console: the tenant/project switcher, Talk (the three
channels — WebRTC voice, web chat, and the phone line on **+1 417 674 3169**),
Sessions, Pipeline, the Supervisor desk, and the shell for Evals. Vite + React +
TypeScript + react-router; no state library, no CSS framework.

**The Supervisor desk** (`/supervisor`) lists every call live on the fleet,
phone calls included. Clicking one joins that room with a short-lived,
subscribe-only ticket from `POST /supervise` and shows the transcript live,
audio muted until you press *listen in*. The supervisor is `hidden` at the SFU,
so the caller is never told anybody joined — and the badge on the screen is the
server's own answer, read back off `list_participants`, not our claim. The
arrival is written into the caller's own log as `supervisor.join`:

```bash
uv run python -m convo sessions show <id> | grep supervisor
```

From that desk a supervisor can also **whisper** to the agent, **take the
line**, and **transfer the call to a phone** — cold (a SIP REFER: the caller
leaves for that number and this job ends) or warm (the colleague is dialled
into the room, briefed where the caller provably cannot hear it, then bridged).
Every verb is one line in the caller's own log, and a transfer carries its mode
and its outcome, so a transfer that did NOT happen is as readable as one that
did. Warm needs an outbound trunk (`SIP_OUTBOUND_TRUNK_ID`) this box does not
have yet and says so instead of failing mid-call; cold needs only
`transfer_mode=enable-all` on the Twilio trunk — `infra/box/README.md` has the
exact toggles, and `scripts/twilio_trunk.py` reports whether they are set.

The same three verbs without a browser, for an escalation rule or a terminal:

```bash
curl -XPOST localhost:8090/supervise/verb -H 'content-type: application/json' \
  -d '{"room":"call-…","identity":"sup:berna","verb":"transfer",
       "mode":"cold","to":"+34600111222"}'
```

Two ways to run it. In development the vite server serves the app and proxies
`/tenants`, `/token`, `/sessions` and `/pipeline` to the control plane:

```bash
uv run uvicorn api:app --port 8090        # terminal 1: the control plane
cd ui && npm install && npm run dev       # terminal 2: http://localhost:5173
```

In production there is one port: build once and `api.py` serves the bundle
itself, with the API paths keeping priority and everything else falling back to
the SPA.

```bash
cd ui && npm install && npm run build     # writes ui/dist (never committed)
uv run uvicorn api:app --port 8090        # http://localhost:8090
```

## Layout

```
worker.py     data plane: one AgentServer, one fleet, every tenant
api.py        control plane (ms-8+): tokens, dispatch, tools hub, call log
core/         runtime: contracts, agents, tools, adapters, state, observability
ui/           the operator console: React + vite, served by api.py once built
tenants/      one folder per customer: adapters + projects (agents, prompts, evals)
infra/        compose/ — the local dev stack (livekit-server + redis)
scripts/      dev_call.py: a browser-less chat call against a running server
tests/        unit tests and ring-1 evals
docs/         how the platform is meant to be used: tenants, prompts, evals
.taskops/reports/  per-milestone learning reports (Markdown)
presentation/ self-narrating deck engine
```

License: Apache-2.0.

## How this repository is orchestrated

The build itself is public. A [taskops](https://pypi.org/project/taskops-cli/)
board holds the plan; this repo carries the board's hooks (`.claude/`,
`.mcp.json`) so any clone can join it.

- **Milestones are chapters.** Each one is small enough for a human to review
  in minutes and ends with a command to run plus `.taskops/reports/ms-N.md`, a
  learning report: what was achieved, what was learned, what was decided.
- **Cards are briefs.** A card carries a spec a stranger could pick up, the
  files it may touch, acceptance criteria, and — when a decision was made — a
  short essay in its thread explaining why.
- **One orchestrator, many workers.** The orchestrator plans, assigns (each
  card gets its own git worktree), reviews the diff in session and merges with
  `--no-ff`. Workers are AI sub-agents, one per brief; the first infrastructure
  cards were done by the orchestrator itself.
- **Humans judge.** Every milestone report leaves an `nvim -p …` command to
  read the code; evaluations (DeepEval) run on every milestone so prompts keep
  a consistent line as the system grows.

Reusable for other teams: the hooks are two lines of JSON, the conventions are
this section, and the pattern (seams first, then parallel cards, HTML report
per milestone) does not depend on any particular framework.

## Production box (convo-box)

The dedicated GCP box (`e2-standard-4`, `lk.bernardocastro.dev`) runs the SFU
stack — livekit-server + livekit-sip + redis, host networking, real keypair
generated on the box on first run:

```bash
./infra/box/setup.sh     # idempotent: install docker, render configs, compose up
```

It also mirrors `LIVEKIT_URL` and the keypair into your local `.env`, so
`python worker.py dev` registers against the box instead of the laptop stack.
