# convo — working agreement for agents

Multi-tenant conversational platform for contact centers: one deploy, many
businesses. Built on self-hosted LiveKit (SFU + SIP + Agents), Anthropic Claude
Haiku (LLM), Soniox (STT), ElevenLabs (TTS). Reply to the user in Spanish; code,
comments, commit messages and this file in English.

**Thesis:** the LLM is a swappable interface driver; the platform is a process
runtime that talks. Control, state, tools, audit and tenancy live in the
backend, never in the prompt.

The system as it is: `ARCHITECTURE.md`. Why each module is the way it is:
`docs/decisions/<module>.md`. Each taskops card carries its own spec.

## Layout (Rails-shaped, standard Python)

```
convo/        the engine, ONE package: cli/ domain/ agents/ prompting/ tools/ session/ providers/
              state/ telephony/ supervision/ scoring/ observability/ lang/ api/ evals/ testing/
tenants/      the apps: <id>/tenant.py, adapters/, projects/<p>/{project.py, prompts/knowledge.md,
              messages.py, helpers.py, stages/*.py, prompts/*.md, evals/}
tests/        unit + tests/evals (DeepEval); tests/fixtures/ shared fakes
docs/         decisions/ evals.md prompts.md tenants.md deck.pdf
infra/        box/ compose/ seed/ scripts/
ui/           React console
```

Mapping, so the vocabulary stays fixed: router → `convo/session/router.py`;
controller → a stage (`stages/x.py`, a `TenantAgent`); model → an adapter;
view → `prompts/x.md`, rendered in the layout `convo/prompting/layout.py` with
partials `prompts/_partials/*.md`; `lib/` → `convo/lang/`; `bin/` → `convo/cli/`.

## Invariants the tests enforce

- No `.py` at the repo root. `convo/` is the only package; entry points are
  `python -m convo <group>` (`convo/cli/`) and `uvicorn convo.api.app:app`.
- `convo/` never imports `tenants/` (`tests/test_core_isolation.py`).
  `convo/session/registry.py` imports each tenant in try/except: a broken
  tenant is unroutable, it does not take the fleet down.
- Projects import `convo.agents` (`TenantAgent`, `ConfirmTask`, …), never
  `livekit.agents` directly. `convo/domain`, `convo/lang`, `convo/state` import
  no framework.
- No file over 400 lines. Docstrings are ONE line: what it does, for whom. The
  argument, the measurement and the history go to `docs/decisions/<module>.md`
  and the module docstring cites it. Two exceptions keep their full text: tool
  docstrings (the schema the model reads) and route docstrings (the JSON the
  client reads).
- A stage prompt is `prompts/<stage>.md`, rendered by `convo.prompting.stage_prompt`
  as `<knowledge_tag>` + view + transfer protocol + `SUPERVISOR_PROTOCOL`, in that
  order. Shared paragraphs are partials included by name; `tests/test_prompts.py`
  pins the composition. `Project.prompts` and `Project.knowledge_tag` say where.
- Spanish calendar words live once, in `convo/lang/es.py`. A tenant imports
  `convo.lang`, never another tenant.
- What a tool says to the model when it cannot do what was asked lives in the
  project's `messages.py`; pure formatting and parsing in `helpers.py`.

## Invariants of the runtime (verified against livekit-agents 1.7.1; do not "fix" them)

- One `AgentServer`, one `@server.rtc_session(agent_name=settings.fleet())`.
  `agent_name` is never empty (empty = implicit dispatch to any anonymous worker).
- Each job is a separate process. No DB/Redis pools in the job process; all
  business IO goes over HTTP to the API (`convo/api/client.py`). `setup_fnc`
  (prewarm) only loads VAD/turn-detector; it has a 10 s budget.
- Tenant identity comes from `ctx.job.metadata` / `ctx.job.attributes` /
  the dialled number / `TENANT` env, resolved by `convo/session/router.py` into
  a single `TenantContext` (`convo/domain/context.py`). The channel (voice|chat)
  belongs to the **session**, not the project.
- Every tool has a `ToolSpec` (`side_effect: read|write|irreversible`,
  `idempotency_key`, `pii_scope`, `timeout_s`, `compensation`, `result_summary`).
  `guard.check` refuses `irreversible` without a `confirmation_token` minted by
  `ConfirmTask`. Tools raise `ToolError(msg)` for user-facing failures.
- Context summary across handoffs happens in `TenantAgent.on_enter` (handoff
  does not copy history).
- Event log is append-only with a per-session `seq`; the stage is appended
  **during** the call (SIGKILL-safe). A shutdown callback writes the report and `session.end`.
- Every voice call keeps its audio through the framework's `RecorderIO`;
  `convo/session/recordings.py` is the ONLY module that composes a recording
  path. Recordings hold PII: out of git, served only by
  `GET /sessions/{id}/recording`. `Project.recording=False` opts out, `RECORD=0`
  a deploy.
- Prompt caching: `anthropic.LLM(model="claude-haiku-4-5", caching="ephemeral")`.
  **Haiku 4.5 only caches prefixes >= 4096 tokens.** Every project's knowledge
  block must clear that floor; never put timestamps or per-request ids in the
  prefix; never reorder tools. `preemptive_generation` is DISABLED (human's
  decision 2026-08-31).
- The date reaches the model as a paired tool call + result
  (`convo.agents.clock.clock_reading`), never as a system message: livekit-agents
  rewrites every system item after the first into a USER turn, and Haiku
  answers it. A supervisor's whisper stays in that instruction channel on
  purpose (context to be OBEYED); context to be READ is a tool result.
- Call `sanitize_tool_pairing(chat_ctx)` before every generation.
- STT: Soniox `stt-rt-v5`, `language_hints=["es","en"]`, endpointing
  `level=2 / sensitivity=0.3 / max_endpoint_delay_ms≈1000`, `sample_rate=16000`
  even on PSTN. Alternative slot: Deepgram Flux `flux-general-multi`.
  Every transcript passes `convo.session.stt_gate` in `TenantAgent.stt_node`.
- TTS: ElevenLabs `eleven_v3_conversational` / `eleven_flash_v2_5`,
  `sync_alignment=True`. Never `eleven_turbo_v2_5`, never `eleven_v3`.
- VAD `inference.VAD(model="silero")`, turn detector `inference.TurnDetector()`.
  VAD `min_silence_duration >= 0.25`. No GPU anywhere.
- Chat mode: `RoomOptions(audio_input=False, audio_output=False)`; agent text
  on `lk.transcription`, user text on `lk.chat`.
- DeepEval: never leave `@observe(metrics=[...])` in production code; hard
  policies use `ConversationalDAGMetric`, not `GEval`; eval rooms are created by
  the API with dispatch metadata.
- Ring 4 (`convo/scoring/`) scores every finished call from the API, never
  from the job process: checks decided by code, then AT MOST one Haiku call
  priced against `SCORING_CAP_EUR` first. `Project.scoring=False` opts out.
- Secrets only from env. Never commit `.env*` except `.env.example`.

## Commands

```
uv sync --extra dev
uv run convo console --text                 # talk to the default project from the keyboard
uv run convo console --tenant tienda-sur --project pedidos
uv run convo api                            # control plane + UI on :8090
uv run convo worker dev                     # the fleet against LIVEKIT_URL
uv run convo sessions list|show <id>
uv run pytest -m unit                       # ring 1
uv run deepeval test run tests/evals -n 3   # ring 1 metrics
uv run convo evals report <tenant> <project>
docker compose -f infra/compose/dev.yml up  # livekit-server --dev + redis
```

## Working on the board (taskops)

- This session's MCP server may be pinned to another repo: pass
  `repo_path=/Users/berna/prueba-abai` on every taskops call.
- Orchestrator plans (`taskops_plan`), assigns (`taskops_assign`), spawns one
  sub-agent per brief, reviews in-session (`taskops_review`) and merges
  (`taskops_merge`). Never raw git merges in the shared checkout; never
  `git switch`. Workers pass `actor=agent:<dev>/<name>` on every call.
- Cards are small and every milestone ends with a command the human runs.
- Commits: `Bernardo Castro <me@bernardocastro.dev>`, no `Co-Authored-By`, no
  generated-with trailers. Versions and tags are the human's call.

## Every milestone ships four things

1. A command the human runs to see it working.
2. `.taskops/reports/ms-N.md`, a learning report, indexed in
   `.taskops/reports/README.md` and filed on the board with `taskops_filed`.
3. DeepEval, incrementally: per-project `goldens.json` grows with every card.
4. An `nvim -p …` command in the closing note of every card.

## Code style

- One responsibility per module, one line per docstring, files under 400 lines.
- Public methods first; private helpers below, prefixed `_`.
- Explicit over clever: no metaprogramming, no hidden globals, no magic imports.
- Python 3.12, `ruff` (line 100), full type hints; dataclasses inside, pydantic
  at process boundaries.
- Tests: `pytestmark = pytest.mark.unit` or `.evals` per module; one behaviour
  per test; names read as sentences; shared fakes in `tests/fixtures/`.

## Voice

Default TTS voice: ElevenLabs `Carolina - Spanish woman - es_ES`
(`UOIqAnmS11Reiei1Ytkc`). Voice is per-project data, never hardcoded in convo.
