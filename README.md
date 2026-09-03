# convo

A multi-tenant conversational platform for contact centers: one deployment,
many businesses, each answering its own phone number and web chat with its own
voice, tools and rules. Built on self-hosted [LiveKit](https://livekit.io)
(SFU, SIP and Agents). Every AI vendor is a slot: Claude Haiku 4.5 or GPT 5.4
mini for the language model, Soniox or Deepgram for speech-to-text, ElevenLabs
for text-to-speech, chosen per project and changeable from the console.

The thesis: the language model is a swappable interface driver. Control,
state, tools, audit and tenancy live in the platform and never in a prompt.
Anything irreversible needs a confirmation token minted from a real "yes";
every call leaves an append-only event log, a recording and a score.

- **How it is built:** [`ARCHITECTURE.md`](ARCHITECTURE.md)
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
docker compose -f infra/compose/dev.yml up -d        # livekit-server on infra/compose/livekit.yml (devkey/secret) + redis
uv run convo api                                     # control plane + console UI on :8090
uv run convo worker dev                              # the fleet: one process, every tenant
open http://localhost:8090                           # the web console
```

Nothing in the worker's environment names a tenant. Who answers is decided
per session by the dispatch metadata inside the token the control plane mints,
by the phone number that was dialled, or by `TENANT`/`PROJECT` on a console.

## The command line

`uv run convo …` and `uv run python -m convo …` are the same thing. Seven
groups; the five with verbs print their usage when called with nothing.

```bash
# talk to a project from this terminal, no server involved
convo console --text                                   # keyboard, default project
convo console --tenant tienda-sur --project pedidos    # microphone, the shop
convo console --record                                 # keeps the OGG under console-recordings/
convo console --list-devices                           # which mic and speaker it would use

# the fleet: one worker process, every tenant, against a LiveKit server
convo worker dev                                       # LIVEKIT_URL from .env, dev log level
convo worker start --drain-timeout 30                  # production: finish live jobs before exit
convo worker download-files                            # fetch the VAD and turn-detector weights ahead of time

# the control plane and the web console
convo api                                              # http://127.0.0.1:8090
convo api --host 0.0.0.0 --port 8090 --reload          # restart on code changes

# read what a call did: every session is an append-only event log
convo sessions list                                    # newest first
convo sessions show AJ_Cfb9uyiixzjC                    # seq / t_ms / kind / payload, PII masked
convo sessions tail                                    # follow the newest session live, then the next one
convo sessions tail AJ_Cfb9uyiixzjC                    # follow one session until it ends
convo sessions eval AJ_Cfb9uyiixzjC --voice            # ring 3: replay it through the project's metrics
convo sessions score AJ_Cfb9uyiixzjC --free            # ring 4: the checks, without the judge

# which phone number reaches which project (a number is a route, never a project)
convo routes list
convo routes seed                                      # infra/seed/routes.json into an empty store
convo routes add cc +14176743169 clinica-norte reagendamiento voice

# the knowledge block: git is the seed, a pinned version overrides it without a deploy
convo versions list
convo versions pin clinica-norte reagendamiento v3 tenants/clinica-norte/projects/reagendamiento/knowledge.md

# the eval rings a person runs (ring 1 in CI runs through pytest and deepeval, below)
convo evals report clinica-norte reagendamiento                    # ring 1 on one project
convo evals report tienda-sur pedidos --model claude-haiku-4-5 --model gpt-5.4-mini
convo evals nightly --dry-run                                      # what tonight would call and cost
convo evals nightly --only clinica-norte/reagendamiento --budget 2 # ring 2: real calls, on a budget
convo evals nightly --api https://lk.example.com --deadline 900 --date 2026-09-03   # another fleet, a shorter night
convo evals record clinica-norte reagendamiento                    # one call through STT, LLM and TTS, recorded
convo evals golden                                                 # regenerate the TTS goldens (billed)
```

## Cheat sheet

Everything you can run, by what you are doing. All from the repo root.

**Set up**

```bash
uv sync --extra dev                              # deps, the convo command, ruff, pytest, deepeval
cp .env.example .env                             # then the keys: ANTHROPIC_API_KEY at least
docker compose -f infra/compose/dev.yml up -d    # local livekit-server (7880/7881/7882-udp) + redis; box.yml is the production stack
cd ui && npm ci && npm run build && cd ..        # the console UI, served by convo api from ui/dist
```

**Run**

```bash
convo console --text                             # one project, this terminal
convo api                                        # control plane + UI on :8090
convo worker dev                                 # the fleet, against LIVEKIT_URL
uv run python infra/scripts/dev_call.py          # a scripted chat call through api + worker, both tenants
uv run python infra/scripts/dev_call.py tienda-sur/pedidos "hola" "¿cuándo llega mi pedido?"
cd ui && npm run dev                             # the UI with hot reload, proxied to :8090 (CONVO_API to retarget)
cd ui && npm run typecheck                       # the UI's only check; CI does not run it
```

**Test**

```bash
uv run ruff check . && uv run ruff format --check .   # what CI lints
uv run pytest -m unit                                 # ring 1, ~3 min; no keys needed
uv run pytest -m unit -k prompts                      # one area
uv run pytest -m "unit and needs_llm"                 # the unit tests that call the model (ANTHROPIC_API_KEY)
uv run pytest -m voice                                # the ones that build STT/TTS sessions (provider keys)
uv run pytest -m evals                                # the DeepEval suites through pytest (ANTHROPIC_API_KEY)
uv run pytest tests/test_template.py                  # copies tenants/_template and proves it routes
```

**Evaluate**

```bash
uv run deepeval test run tests/evals -n 3             # ring 1 metrics, every tenant + cross-tenant leakage
uv run deepeval test run tenants/tienda-sur/projects/pedidos/evals/test_ring2.py   # ring 2, one project
convo evals report <tenant> <project> [--model M]     # ring 1 report + model matrix, tmp/reports/
convo evals nightly [--dry-run] [--only t/p] [--budget N]   # ring 2 against CONVO_API, tmp/evals/
convo sessions eval <id> [--voice]                    # ring 3: one real call, replayed through the metrics
convo sessions score <id> [--free]                    # ring 4 by hand; the api's sweeper does it alone
convo evals record [<tenant> <project>]               # one recorded call for the voice metrics
convo evals golden                                    # TTS goldens under tmp/golden
uv run python infra/scripts/seed_board_demo.py        # three real transactions into CONVO_DB, for the Board
```

**Operate the box** (`BOX=convo-box`, an ssh alias; override with `BOX=…`)

```bash
./infra/box/setup.sh                             # once: docker, LiveKit keypair, SFU + SIP + redis
./infra/box/deploy_worker.sh                     # code, deps, .env, phone route, convo-worker.service
./infra/box/deploy_api.sh                        # code, UI build, Caddy, convo-api.service, evals timer
ssh convo-box 'systemctl is-active convo-api convo-worker convo-evals.timer'
ssh convo-box 'journalctl -u convo-worker -n 50 -o cat'
ssh convo-box 'sudo systemctl start convo-evals.service'          # one night of ring 2 by hand
ssh convo-box 'cd ~/convo-app && uv run convo evals nightly --dry-run'
uv run python infra/scripts/twilio_trunk.py --number +14176743169 --dry-run   # the phone path, read only
uv run python infra/scripts/twilio_trunk.py --number +14176743169 --trunk-name convo --twilio-env ~/.twilio.env
uv run python infra/scripts/sip_probe.py --dialled +14176743169                # one SIP INVITE at the box
uv run python infra/scripts/isolation_probe.py --phase 4                       # can the SFU hide a briefing?
```

**Environment variables that change behaviour**

| variable | default | what it does |
|---|---|---|
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | unset | the agent's model and the judge; without the first, `needs_llm` tests skip |
| `SONIOX_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY` | unset | STT and TTS; absent, a session is text-only |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | `ws://localhost:7880`, `devkey`, `secret` | the SFU the worker and api talk to |
| `LIVEKIT_PUBLIC_URL` | `LIVEKIT_URL` | the url minted into browser tokens |
| `TENANT`, `PROJECT` | unset | force a project on a console |
| `DEFAULT_TENANT`, `DEFAULT_PROJECT` | `clinica-norte`, `reagendamiento` | what a console talks to when nothing names one |
| `FLEET` | `cc` | the agent name the worker registers as; the SIP dispatch rule names it |
| `CONVO_DB` | `tmp/convo.db` | the SQLite store (sessions, routes, versions, eval runs) |
| `CONVO_RECORDINGS` | `tmp/recordings` | where call audio lands |
| `RECORD` | unset | exactly `0` records nothing for a whole deploy |
| `CONVO_LEDGER` | `tmp/business.json` | the demo adapters' business file |
| `RECORDINGS_TOKEN` | empty | bearer required by `GET /sessions/{id}/recording` |
| `CONVO_API` | `http://127.0.0.1:8090` | the control plane evals file their runs with |
| `CONVO_SEED_ROUTES` | `infra/seed/routes.json` | the phone routes `convo routes seed` writes |
| `SCORING_SWEEP` | `1` | `0` disables ring 4; `SCORING_SWEEP_S` (`10`), `SCORING_BATCH` (`3`), `SCORING_WINDOW_S` (`86400`) pace it |
| `SCORING_CAP_EUR`, `SCORING_JUDGE_THRESHOLD` | `0.01`, `0.7` | the judge's price ceiling per call and its pass mark |
| `DEEPEVAL_JUDGE_MODEL`, `SCORING_JUDGE_MODEL` | `claude-haiku-4-5` | the judge for evals and for ring 4 |
| `CONVO_EVAL_MODEL` | unset | the model the eval harness drives instead of the project's |
| `SIP_OUTBOUND_TRUNK_ID`, `TRANSFER_TO`, `TRANSFER_RINGING_S` | unset, unset, `25` | warm transfer: the trunk, a fallback number, how long to ring |
| `SIP_WAIT_S` | `5` | how long a job waits for the SIP caller's attributes |
| `ANTHROPIC_WORKSPACE_ID` | unset | only for workspace-scoped Anthropic keys |
| `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN`, or `TWILIO_API_KEY` + `TWILIO_API_SECRET` | unset | `infra/scripts/twilio_trunk.py` only |
| `CONVO_ENV` | unset | the environment banner the UI shows |
| `BOX` | `convo-box` | the ssh host every `infra/box/*.sh` deploys to |

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
shutdown callback ───────── close_log writes session.end; convo/scoring/sweeper.py judges it from the api
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
  agents/         TenantAgent (a stage), ConfirmTask, the clock the model reads, the transfer tool
  adapters/       the adapter protocol, the human adapter, the demo ledger
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
                            stages/*.py · prompts/*.md (+ confirm/, and a _partials folder such as _reception/) · evals/
tests/            unit tests (ring 1) and tests/evals (DeepEval); tests/fixtures/ shared fakes
docs/             decisions/, evals.md, prompts.md, tenants.md, deck.pdf
infra/            box/ (systemd, Caddy, deploy scripts), compose/, seed/, scripts/
ui/               the React console
```

Rules the tests enforce (`tests/test_core_isolation.py`, `tests/test_layout.py`):
no `.py` at the repo root; `convo/` never imports `tenants/`; a tenant never
imports `livekit` directly; no tracked `.py` over 400 lines. By convention:
every docstring is one line, and the reasoning lives in `docs/decisions/`.

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
