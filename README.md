# convo

A multi-tenant conversational platform for contact centers: one deployment,
many businesses, each answering its own phone number and web chat with its own
voice, tools and rules. Built on self-hosted [LiveKit](https://livekit.io)
(SFU, SIP and Agents), Anthropic Claude for the language model, Soniox for
speech-to-text and ElevenLabs for text-to-speech.

The thesis: the language model is a swappable interface driver. Control,
state, tools, audit and tenancy live in the platform and never in a prompt.
Anything irreversible needs a confirmation token minted from a real "yes";
every call leaves an append-only event log, a recording and a score.

- **Design and evidence:** [`REPORT.md`](REPORT.md)
- **Why the code is the way it is:** [`docs/decisions/`](docs/decisions/README.md)
- **Adding a business:** [`tenants/_template/README.md`](tenants/_template/README.md)
- **How the agent is measured:** [`docs/evals.md`](docs/evals.md)

## Quickstart

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), an
`ANTHROPIC_API_KEY`. Voice on a laptop additionally needs `SONIOX_API_KEY` and
`ELEVENLABS_API_KEY`; the phone path needs a LiveKit server and a SIP trunk
(see [`infra/box/README.md`](infra/box/README.md)).

```bash
git clone https://github.com/bernatch22/convo-platform.git && cd convo-platform
uv sync --extra dev
cp .env.example .env            # then fill in the keys you have

uv run convo console --text                          # type to the clinic's receptionist
uv run convo console --tenant tienda-sur --project pedidos --text
uv run convo console                                 # your microphone, the agent's voice
uv run convo console --record                        # the same, keeping the OGG
```

The console talks to one project directly, with no server in between. The
full stack is three processes:

```bash
docker compose -f infra/compose/dev.yml up -d        # livekit-server --dev + redis
uv run convo api                                     # control plane + console UI on :8090
uv run convo worker dev                              # the fleet: one process, every tenant
open http://localhost:8090                           # the web console
```

Nothing in the worker's environment names a tenant. Who answers is decided
per session by the dispatch metadata inside the token the control plane mints,
by the phone number that was dialled, or by `TENANT`/`PROJECT` on a console.

## The command line

```
convo console   talk to a project from this terminal (--text, --record, --tenant, --project)
convo worker    dev | start: run the fleet against a LiveKit server
convo api       run the control plane and the web console
convo sessions  list | show <id> | eval <id> | tail <id>: read a session's event log
convo routes    list | seed | add <fleet> <number> <tenant> <project> [voice|chat]
convo versions  list | pin <tenant> <project> <version> [<file>]: the knowledge override
convo evals     report | nightly | record | golden: the eval rings a person runs
```

`uv run convo …` and `uv run python -m convo …` are the same thing.

## How a call moves through the code

```
PSTN / browser
      │
      ▼
convo/worker.py ─────────── entrypoint(ctx)
      ▼
convo/session/router.py ── resolve(ctx): whose job is this? → TenantContext
      ▼
convo/session/build.py ─── AgentSession(STT, LLM, TTS, VAD)   ← convo/providers/
      ▼
tenants/<t>/projects/<p>/project.py ── entry_agent(tc) → the first stage
      ▼
stages/identify.py ──────── a TenantAgent: its prompt is prompts/identify.md
      │                      rendered by convo/prompting/layout.py
      │   the caller speaks → stt_gate → the model calls a tool
      ▼
@function_tool ──────────── tc.tools.call("find_patient", …)
      │                        ├─ convo/tools/guard.py    irreversible? token?
      │                        ├─ adapters/patients.py    the customer's own system
      │                        └─ convo/state/log.py      one append-only line per event
      ▼
return self.hand_off(ChooseSlot(tc)) ── the next stage; the log records the handoff
      ▼
ConfirmTask ─────────────── "…¿lo confirmo?" → a one-shot token → Saga: cancel, book, SMS
      ▼
on_session_end ──────────── the report; convo/scoring/ judges the call from the API
```

A **stage** is one phase of a conversation: a LiveKit `Agent` with its own
prompt and its own tools, and a stage moves the call on by returning the next
one from a tool. Rails readers will recognise the shape: the router resolves,
a stage is the controller, adapters are the models, and a prompt is the view,
rendered in a layout with partials.

## Layout

```
convo/            the engine, one installable package
  cli/            one module per command group
  domain/         Tenant, Project, TenantContext, ToolSpec, catalog: contracts, no framework
  agents/         TenantAgent (a stage), ConfirmTask, the clock the model reads
  prompting/      the layout every prompt renders in, Markdown views and partials, the protocols
  tools/          guard, executor, saga, confirmation tokens, the default failure sentences
  session/        router, registry, session build, pipeline, rooms, SIP, STT gate, recordings
  providers/      llm, stt, tts, turn: the only modules that name a vendor
  state/          the append-only log, the store (sqlite, memory), overrides, outcomes
  telephony/      lines, cold and warm transfer, handover, audio isolation
  supervision/    a second human on a live call: control, monitor, desk
  scoring/        ring 4: every finished call scores itself, off the job process
  observability/  latency, prices, timed words
  lang/           es.py: Spanish calendar words, one copy
  api/            the control plane: app.py and one router per resource
  evals/          suites, goldens, runs and the runner the console launches
  testing/        the harness and the metric shapes tenants' evals import
tenants/          the businesses: _template/, clinica-norte/, tienda-sur/
  <id>/tenant.py            id, name, region, build_adapters()
  <id>/adapters/            one class per system the business runs
  <id>/projects/<p>/        project.py · knowledge.md · messages.py · helpers.py
                            stages/*.py · prompts/*.md (+ _partials, confirm/) · evals/
tests/            unit tests (ring 1) and tests/evals (DeepEval); tests/fixtures/ shared fakes
docs/             decisions/, evals.md, prompts.md, tenants.md, deck.pdf
infra/            box/ (systemd, Caddy, deploy scripts), compose/, seed/, scripts/
ui/               the React console
```

Rules the tests enforce: no `.py` at the repo root; `convo/` never imports
`tenants/`; a project imports `convo.agents`, never `livekit` directly; no
file over 400 lines; every docstring is one line, the reasoning lives in
`docs/decisions/`.

## Adding a business

```bash
cp -r tenants/_template tenants/<your-id>
grep -rl 'example-co' tenants/<your-id> | xargs sed -i '' 's/example-co/<your-id>/g'
uv run convo console --tenant <your-id> --project example --text
```

Then follow [`tenants/_template/README.md`](tenants/_template/README.md): one
adapter per system, a `ToolSpec` per capability with its side effect declared,
one stage per phase of the call, one Markdown prompt per stage, a knowledge
sheet over 4,096 tokens (the prompt-cache floor of Claude Haiku), and goldens.
`tests/test_template.py` performs that copy and proves it routes, renders and
scans its own register.

## Testing

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m unit                                # ring 1: fast, no keys, ~3 minutes
uv run deepeval test run tests/evals -n 3            # ring 1 metrics: needs ANTHROPIC_API_KEY
uv run convo evals report clinica-norte reagendamiento   # one project, HTML under tmp/reports
uv run convo evals nightly --dry-run                 # ring 2: what a night against the box would spend
```

Four rings, each cheaper than the next: unit tests over the harness (no
network), DeepEval metrics over goldens (one judge call at most per case),
synthetic callers against a deployed fleet, and a post-call score written into
every real session's log. [`docs/evals.md`](docs/evals.md) has the detail.

## Deploying

`infra/box/` holds everything a single VM needs: `setup.sh` stands the box up,
`deploy_worker.sh` and `deploy_api.sh` ship the two processes under systemd
behind Caddy, and `infra/scripts/twilio_trunk.py` wires a phone number to the
fleet's dispatch rule. Phone routes a fresh database is seeded with live in
`infra/seed/routes.json`. See [`infra/box/README.md`](infra/box/README.md).

## Licence

Apache 2.0.
