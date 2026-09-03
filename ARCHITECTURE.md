# Architecture

convo is a multi-tenant conversational platform for contact centers. One
deployment serves many businesses; each business answers its own phone number
and web chat with its own voice, knowledge, tools and rules, and none of them
can see another. The platform is built on self-hosted LiveKit for media, SIP
and agent dispatch, and treats every AI vendor as a slot: Claude or GPT for the
language model, Soniox or Deepgram for speech-to-text, ElevenLabs for
text-to-speech.

The thesis that shapes every module: **the language model is an interface
driver, not the system.** Control, state, tools, consent, audit and tenancy
live in the platform. The model is handed a rendered prompt and a small set of
declared tools; what it may do, what it must ask first, what gets written and
what gets remembered are decided in code and recorded in an append-only log.

This document describes the system as it is. The reasoning behind each
decision lives next to the module that made it, in [`docs/decisions/`](docs/decisions/README.md).

## 1. System view

```
                    ┌──────────────────────── the box ────────────────────────────┐
  PSTN ──Twilio──►  │  livekit-sip ──► livekit-server (SFU) ◄── redis              │
                    │                        ▲   ▲                                  │
  browser ─────────►│  Caddy ──/rtc,/twirp──┘   │ dispatch (agent_name = FLEET)    │
        (https)     │    │                       ▼                                  │
                    │    └── everything else ──► convo api :8090 ◄──── convo worker │
                    │                             │  ▲                 (one process │
                    │                             │  │ same SQLite      per job)    │
                    │                             ▼  │                              │
                    │                          tmp/convo.db   tmp/recordings/       │
                    │                             ▲                                  │
                    │            convo-evals.timer (04:00) ──► ring 2 ── files runs  │
                    └────────────────────────────────────────────────────────────────┘
```

Three processes of our own, plus LiveKit's:

| process | what it is | entry |
|---|---|---|
| **worker** | the data plane: one `AgentServer` registered under the fleet name; LiveKit hands it a job per room, and each job is its own OS process | `convo worker start` |
| **api** | the control plane: mints session tokens with the agent dispatch inside, serves the console, reads every stored session, runs the post-call scorer | `convo api` |
| **evals** | a one-shot systemd unit on a timer: synthetic callers phone the deployed fleet, the results are filed with the api | `convo evals nightly` |

The worker and the api share one SQLite file. The worker writes every event
of a call as it happens; the api reads them back for the console and appends
the score once the call is over. There is no queue and no message bus between
them: the log is the interface.

## 2. Tenancy

A **tenant** is a business. A **project** is one use case of that business:
a phone reception, an order desk. The platform ships two demo tenants
(`clinica-norte/reagendamiento`, `tienda-sur/pedidos`) and a template.

**Discovery.** `convo/session/registry.py` imports every `tenants/<id>/tenant.py`
that exposes a `TENANT`, each in its own try/except, skipping folders whose
name starts with `_` or `.`, so the template is never routable. A tenant that
fails to import is unroutable; it never takes the fleet down. Nothing under `convo/`
imports `tenants/`, and a test enforces it.

**Resolution.** When a job arrives, `convo/session/router.py` decides whose it
is, in this order, first answer wins:

1. the job's dispatch metadata, a `SessionMeta` JSON written into the token by the api;
2. the dispatch attributes `convo.tenant`, `convo.project`, `convo.channel`;
3. the dialled phone number, looked up in the `routes` table for this fleet;
4. `TENANT` and `PROJECT` in the environment, which is how a console picks.

The result is one `TenantContext` (`convo/domain/context.py`): tenant, project,
channel, session id, the day, the tenant's adapters, a tool executor, the open
event log, and per-session state such as the identified customer and the PII
values learned so far. It travels with the session as `userdata` and reaches
every tool as `ctx.userdata`.

**The channel belongs to the session, not the project.** The same project
answers a phone call and a web chat; only the session says which one this is.

**What a tenant owns and what the platform owns** is a fixed line, written up
in [`docs/tenants.md`](docs/tenants.md): the platform owns shapes (the agent
base, the tool contract, the guard, the saga, the log, the metric graphs), a
tenant owns words (its prompts, its knowledge, its register, its adapters, its
goldens). A project that finds itself writing a router branch or a retry loop
has found a shape missing from the platform.

## 3. The anatomy of a call

```
  caller
    │ audio / text
    ▼
  convo/worker.py            entrypoint(ctx)
    ▼
  convo/session/router.py    resolve(ctx) → TenantContext
    ▼
  convo/session/build.py     AgentSession(STT, LLM, TTS, VAD, turn detector)   ← convo/providers/
    ▼
  project.entry_agent(tc)    the first stage
    ▼
  ┌─ stage ─────────────────────────────────────────────────────────────────┐
  │ prompt = convo/prompting/layout.py renders prompts/<stage>.md            │
  │ on_enter: clock note · previous stage's summary · greeting or first turn │
  │                                                                          │
  │ caller speaks ─► stt_gate ─► model ─► @function_tool                     │
  │                                         │                                │
  │                                         ▼                                │
  │                              tc.tools.call(name, args)                   │
  │                                 ├─ guard: side effect? token?            │
  │                                 ├─ adapter: the business's own system    │
  │                                 └─ log: tool.call / tool.result          │
  │                                                                          │
  │ return self.hand_off(NextStage(tc)) ─► stage.handoff in the log          │
  └──────────────────────────────────────────────────────────────────────────┘
    ▼
  ConfirmTask   "…¿lo confirmo?" ─► caller says yes ─► one-shot token ─► Saga
    ▼
  session end   report · session.end · (later, from the api) session.score
```

A **stage** is one phase of a conversation: a LiveKit `Agent` with its own
prompt and its own tools. A stage moves the call on by returning the next
stage from a tool, so every transition is a thing that happened and is in the
log, never a flag somebody set. Readers who know Rails will recognise the
shape: the router resolves, a stage is the controller, an adapter is the model,
a prompt is the view.

## 4. The conversation runtime

**`TenantAgent`** (`convo/agents/stage.py`) is the base of every stage and the
only place a project touches the agent framework. It owns four moments:

- `on_enter`: put the day in front of the model once per session, inherit the
  previous stage's `summary()`, record the stage, then speak the project's
  greeting (first stage) or open a turn.
- `stt_node`: every transcript passes a gate that refuses a "final" with no
  voiced audio behind it and logs it as `stt.phantom`. Streaming STT invents
  sentences over comfort noise; the gate measures frames, never phrases.
- `on_user_turn_completed`: the turn boundary. A supervisor's queued note is
  applied here; while a human holds the line the agent's reply is cancelled;
  a murmur that landed on the agent's own voice is dropped.
- `hand_off`: returns the next stage, records the transition, and by default
  says nothing, because the arriving stage speaks in its own `on_enter`.

**Handoffs carry a summary, not a transcript.** LiveKit copies no history
across a handoff. The arriving stage writes one prose line about what happened
before into its own context, prefixed with a fixed instruction not to greet
again. What the caller already said travels; the whole transcript does not.

**Prompts are views.** A stage's prompt is `prompts/<stage>.md`. The layout
(`convo/prompting/layout.py`) renders every prompt the same way:

```
<knowledge_tag>                 the project's stable knowledge sheet, or the pinned override
  …
</knowledge_tag>

<the view>                      role · <instructions> · <examples>; shared paragraphs are
                                {% include "_partials/x.md" %} lines, expanded by name
<transfer protocol>             only when the project declares a transfer number
<supervisor protocol>           always last: the paragraph that lets a whisper outrank the script
```

The knowledge block comes first because it is the prompt-cache prefix: it must
be long and it must never change within a day. Nothing dated, numbered or
per-request enters a prompt.

**The date is evidence, not speech.** Today's date reaches the model as a
paired tool call and result inserted before the first turn
(`convo/agents/clock.py`), plus a real clock tool the model can call for the
time. A system message added mid-conversation is rewritten by the framework
into a caller turn, and the model answers it; a tool result is the one shape
in a chat context nobody said.

**Consent is an artefact.** When a stage is about to do something
irreversible, it runs `ConfirmTask` (`convo/agents/confirm_task.py`): a tiny
agent that speaks a sentence the platform rendered from the row it is about
to write, and waits for a yes or a no through two tools. A yes mints a
one-shot token bound to exactly that tool and those arguments; a no records
the refusal. The model never writes the confirmation sentence and never
decides the caller agreed.

## 5. Tools

Every tool a project can call is declared in a `ToolSpec`
(`convo/domain/tools.py`) and collected in the project's `ToolCatalog`. A tool
missing from the catalog cannot run, however convincingly the model asks.

| field | what it declares |
|---|---|
| `side_effect` | `read`, `write` or `irreversible` |
| `idempotency_key` | the argument that makes a retry the same call |
| `pii_scope` | which arguments are personal data, masked in the log |
| `timeout_s` | how long the adapter may take |
| `compensation` | the tool that undoes this one, for the saga |
| `requires_confirmation` | ask first even when the effect is not irreversible |
| `result_summary` | the one line of a result the log is allowed to keep |
| `infrastructure` | platform plumbing such as the clock, not one of the business's own tools |

The path from the model's call to the business's system
(`convo/tools/executor.py`): look the spec up, learn the PII values in the
arguments, mask the call's own log line, run the **guard**
(`convo/tools/guard.py`), call the **adapter** with the unmasked arguments
under the timeout, log the result's shape and summary. Any failure becomes a
`tool.error` event and a sentence the model reads; an adapter's own
`ToolError` reaches the model untouched.

**The guard** refuses any tool whose spec declares a non-positive
`timeout_s`, and refuses a tool that needs confirmation when the token is
missing, already spent, past its two minutes, or minted for a different call
or different arguments. The executor spends the token only
after a successful call, so a refused booking can be retried within the
window without asking again.

**The saga** (`convo/tools/saga.py`) runs several writes as one: release the
old hour, take the new one, send the SMS. A failure halfway compensates every
completed step in reverse using each spec's declared `compensation`, and
records what it undid and what it could not.

**Adapters** (`convo/adapters/base.py`) are the business's own systems behind
one protocol: `capabilities()` and `execute(capability, args)`. The executor
picks whichever adapter declares the capability a tool asks for, so adding a
system is adding an adapter, not touching a stage. The demo tenants ship fakes
with deterministic failures; a real customer swaps the class.

## 6. State

**The event log** is the memory of a call and the evidence of everything else.
`convo/state/log.py` appends `Event(seq, kind, t_ms, payload)` rows with a
per-session sequence, scrubbing every payload against the PII the session has
learned. The stage, every turn, every tool call and result, every consent
grant, every handoff and every supervisor verb land during the call, not at
its end, so a killed process leaves a log that stops at the truth.

**The store** (`convo/state/store/`) is a protocol with two backends: SQLite
for a laptop and the box, memory for tests. The SQLite backend runs in WAL
mode with two triggers that abort any `UPDATE` or `DELETE` on the events
table. Tables: sessions, events, routes, project_versions, pipeline_overrides,
eval_runs.

**Overrides without a deploy.** Six project fields, the voice, the TTS model,
the greeting, the STT provider, the LLM model and the transfer number, may be
changed from the console. `convo/state/overrides.py` applies the stored rows
on the way out of the router, and the session's first event records which
version of the knowledge it ran with. The knowledge sheet itself follows the
same rule: git is the seed, a pinned `project_versions` row is the override.

**Outcomes** (`convo/state/outcomes.py`) are derived from the log at read
time: an irreversible tool call is a transaction, its result decides done,
failed or pending, and the console's board is a query, not a table anyone
maintains.

**Recordings.** Every voice call keeps its audio through the framework's own
recorder, aimed at `CONVO_RECORDINGS/<session_id>/audio.ogg` while the call is
still going. `convo/session/recordings.py` owns the recording root and that
path shape; the only path composed elsewhere is the console's own session
directory in `convo/worker.py`. Recordings hold personal data: they never live in git, are
never a static mount, and are served only by `GET /sessions/{id}/recording`
from a validated id, behind a token when the deploy sets one. A project can
opt out; a deploy can switch recording off.

## 7. Providers as slots

`convo/providers/` is the only package that builds a vendor's client; model
ids also appear in the price table and as the judge's default. Each capability
is one module exposing one factory that reads the project's data and the
environment. STT and TTS return nothing when their key is absent, so a laptop
with only a language-model key still runs a text session; the LLM factory
refuses outright, naming the variable.

| slot | default | alternative | project field |
|---|---|---|---|
| LLM | Claude Haiku 4.5 | GPT 5.4 mini | `llm_model` |
| STT | Soniox `stt-rt-v5` | Deepgram Flux `flux-general-multi` | `stt_provider` |
| TTS | ElevenLabs `eleven_v3_conversational` | `eleven_flash_v2_5` (latency profile) | `tts_model`, `voice`, `stage_voices` |
| VAD, turn detection | Silero VAD and LiveKit's turn detector, through the SDK's inference path with a local fallback | | |

Two facts of the LLM slot shape the prompts: Anthropic caches a prompt prefix
only from 4,096 tokens, OpenAI from 1,024, so every project's knowledge sheet
is long by design; and speculative generation is off, because with semantic
end-of-turn detection it never hid the model's latency and only spent calls.

Voice, model, provider, greeting, language and vocabulary are project data.
Every API key is environment only, and a refusal names the variable, never
the value.

## 8. Telephony and supervision

**Lines are routes.** A phone number is a row in the `routes` table mapping a
fleet and a number to a project and a channel, seeded from
`infra/seed/routes.json` one row at a time, skipping any key already stored,
and listed, seeded and added to with `convo routes`.
The SIP dispatch rule on the box names only the fleet; which business answers
is decided per call by the router. Two tenants on one trunk differ by one row.

**Transfer to a person** (`convo/telephony/`) has two moves. A cold transfer
REFERs the caller's own SIP leg to the number and reads the carrier's answer
into an outcome: transferred, no answer, busy, rejected, unreachable. A warm
transfer dials the colleague into the room, cuts the caller's subscription to
the agent and the colleague while the agent briefs them, then reopens the
audio, the agent's own track included, and tells the agent in a system note
that it no longer speaks. The isolation primitive is server-side
subscription control; it was measured in audio frames before being relied on.
The agent is offered the `transfer_to_human` tool only when the project
declares a transfer number, and the paragraph that teaches the verb arrives and
leaves with the tool.

**A second human on the call.** The api mints supervisor tickets with one of
three capabilities: `listen` (hidden, subscribe only), `whisper` (data
channel, hidden), `takeover` (publish, visible). Verbs travel on a data topic
and on room RPC, and every one is gated by the identity prefix the token
carries. `steer` puts a note in the mid-conversation instruction channel where
the model obeys it; `takeover` silences the agent until `release`, which hands
the human's interval back to the model as context; `transfer` is the verb
above. Every verb is one line in the caller's own log, continuing its sequence.

## 9. Observability and scoring

Every turn carries its timings: transcription delay, end-of-turn delay, time
to first token, time to first byte of speech, end-to-end latency. The agent's
spoken words are timed against the recording. Usage is priced per model from
one table (`convo/observability/prices.py`) and written into the session
report.

**Ring 4** (`convo/scoring/`) scores every finished call from the api, never
from the job process. Four checks are decided by code over the log: consent
before every irreversible write, the register the project declares, no words
of the business next door, no provider errors. Then at most one judge call,
whose worst-case cost is priced against a cap before it is made and which is
skipped under three turns. The verdict is one more append-only event,
`session.score`, at the next sequence number, and a second scorer that raced
the first simply loses. The sweeper runs inside the api process so that it
stops when the api stops.

## 10. Evaluation rings

| ring | what runs | where |
|---|---|---|
| 1 | unit tests over an in-process harness, then DeepEval metrics over each project's goldens, one judge call at most per case | laptop, CI on every push |
| 2 | synthetic callers, with voice, join rooms on the deployed fleet minted at `POST /evals/rooms`, no trunk and no phone number, on a budget of eight live conversations a night | the box, nightly at 04:00 Europe/Madrid, or by hand |
| 3 | one real call replayed through the project's metrics | `convo sessions eval <id>` |
| 4 | the post-call score above, unasked | the api, within a minute of hangup |

The metric shapes are the platform's (`convo/testing/metrics/`): decision
graphs where a deterministic node reads the transcript and a judgement node
answers one narrow question. Consent is read off the turn the write ran in
and the sentence before it; grounded facts are checked against the tool
results in the call; register and leakage are word scans. A project supplies
words: its goldens, its forbidden forms, its neighbour's nouns, its criteria.
Each run is filed with the api and drawn by the console.

## 11. The control plane

`convo/api/` is a FastAPI app with one router per resource; the SPA of the
console is mounted last so it never shadows an endpoint.

| resource | endpoints |
|---|---|
| tokens | `POST /token`: a session ticket with the agent dispatch and the `SessionMeta` inside |
| tenants | `GET /tenants`: what this deploy serves |
| sessions | `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/score`, `GET /sessions/{id}/recording`, `GET /sessions/{id}/live` (SSE), `GET /live-calls` |
| reservations | `GET /outcomes` off the log, `GET /reservations` off the business's own systems |
| supervise | `POST /observe`, `POST /supervise`, `POST /supervise/entered`, `POST /supervise/verb` |
| pipeline | `GET`/`PUT /pipeline/{tenant}/{project}`: the overridable fields and their lines |
| evals | `POST /evals/rooms`, `GET /evals/suites`, `GET /evals/goldens/…`, `GET`/`POST /evals/runs`, `POST /evals/run`, `GET /evals/run/{id}` |

Every handler that reads state opens its own store for the request; `/token`
and `/tenants` read none, and the eval runner keeps a store of its own because
a run outlives the request. Route docstrings document
the exact JSON each returns; the console's TypeScript types are written from
them.

## 12. Deployment

One VM runs everything: four containers under host networking (LiveKit server,
LiveKit SIP, Redis on loopback, Caddy) and three systemd units of our own
(`convo-worker`, `convo-api`, `convo-evals` with its timer). Caddy terminates
TLS, sends `/rtc`, `/twirp`, `/validate` and every websocket upgrade to the
SFU and everything else to the api.
`infra/box/` holds the units, the Caddyfile, the templates for the LiveKit and
SIP configs, and three scripts: `setup.sh` stands the box up once,
`deploy_worker.sh` and `deploy_api.sh` ship the two long-running processes
idempotently from a laptop, and `deploy_api.sh` also installs the nightly evals
unit and its timer. The phone path, a Twilio elastic SIP trunk into the box's SIP
service and a dispatch rule that names the fleet, is wired by
`infra/scripts/twilio_trunk.py`, which reads first and creates only what is
missing.

CI lints and runs ring 1 on every push; the DeepEval job runs only when the
repository holds a language-model key.

## 13. Security and privacy

- **PII is masked by value, not by field.** The executor learns personal
  values from tool arguments declared in `pii_scope` and from results, and
  every log line is scrubbed against them, including free text no contract
  described. Real adapters receive unmasked values; the log never does.
- **Results are summarised, not stored.** A tool result leaves its shape and
  one adapter-rendered line in the log, capped in length.
- **Consent is a token** bound to a tool and a digest of its arguments, single
  use, two minutes, minted only by the confirmation task.
- **Tokens are room-scoped.** Session tickets carry the dispatch; supervisor
  tickets carry one capability and expire in fifteen minutes; the SFU's own
  attributes, not the request body, say what a participant may do.
- **Recordings** are outside git, path-validated, and served by one endpoint.
- **Secrets come from the environment.** Only `.env.example` is versioned.
- **Tenants cannot reach each other.** The platform never imports a tenant, a
  tenant never imports another, and a leakage metric asks each business for
  what only the other one does.

## 14. Where things are

```
convo/            the engine, one installable package
  cli/            convo console | worker | api | sessions | routes | versions | evals
  domain/         Tenant, Project, TenantContext, ToolSpec, the catalog: no framework
  agents/         TenantAgent, ConfirmTask, the clock, the transfer tool
  adapters/       the adapter protocol, the human adapter, the demo ledger
  prompting/      the layout, the Markdown renderer, the protocols
  tools/          guard, executor, saga, confirmation tokens, failure sentences
  session/        router, registry, session build, pipeline, rooms, SIP, STT gate, barge-in, history, recordings
  providers/      llm, stt, tts, turn
  state/          events, the log, attach, the store, overrides, outcomes
  telephony/      lines, transfer, handover, isolation
  supervision/    control, monitor, desk, the supervisor vocabulary
  scoring/        ring 4
  observability/  timings, prices, timed words
  lang/           Spanish calendar words
  api/            the control plane
  evals/          suites, goldens, runs, filing, the runner the console launches
  testing/        the harness, the callers, the metric shapes, replay, reports
tenants/          _template/, clinica-norte/, tienda-sur/
tests/            ring 1
docs/             decisions/, evals.md, prompts.md, tenants.md, deck.pdf
infra/            box/, compose/, seed/, scripts/
ui/               the console
```

How to run any of it is in [`README.md`](README.md). Why any of it is the way
it is, with the measurements that decided it, is in
[`docs/decisions/`](docs/decisions/README.md).
