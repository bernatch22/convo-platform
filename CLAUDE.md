# convo-platform — working agreement for agents

Multi-tenant conversational platform for contact centers: one deploy, many
businesses. Built on self-hosted LiveKit (SFU + SIP + Agents), Anthropic Claude
Haiku (LLM), Soniox (STT), ElevenLabs (TTS). Reply to the user in Spanish; code,
comments, commit messages and this file in English.

**Thesis:** the LLM is a swappable interface driver; the platform is a process
runtime that talks. Control, state, tools, audit and tenancy live in the
backend, never in the prompt.

Full design and evidence: `REPORT.md`. Each taskops card carries its own spec
and, when a decision was made, a short essay in its thread.

## Invariants (verified against livekit-agents 1.7.1 — do not "fix" them)

- Repo root has exactly two loose `.py` files: `worker.py` (data plane) and
  `api.py` (control plane). Nothing else at root.
- One `AgentServer`, one `@server.rtc_session(agent_name=os.getenv("FLEET","cc"))`.
  `agent_name` is never empty (empty = implicit dispatch to any anonymous worker).
- Entry point ends with `cli.run_app(server)` (`server.run()` is async).
- Each job is a separate process (spawn/forkserver). No DB/Redis pools in the
  job process; all business IO goes over HTTP to `api.py` (`core/control_plane.py`).
  `setup_fnc` (prewarm) only loads VAD/turn-detector; it has a 10 s budget.
- `core/` never imports `tenants/` (`tests/test_core_isolation.py` enforces it).
  `core/registry.py` imports each tenant in try/except: a broken tenant is
  unroutable, it does not take the fleet down.
- Projects import `core.agents` (`TenantAgent`, `ConfirmTask`, …), never
  `livekit.agents.voice` directly. The framework is replaceable from one package.
- Tenant identity comes from `ctx.job.metadata` / `ctx.job.attributes` (dispatch
  rule, JWT `RoomAgentDispatch`), resolved by `core/router.resolve(ctx)` into a
  single `TenantContext` (`core/context.py`) — the only definition of that object.
  The channel (voice|chat) belongs to the **session**, not the project.
- Every tool has a `ToolSpec` (`side_effect: read|write|irreversible`,
  `idempotency_key`, `pii_scope`, `timeout_s`, `compensation`). `guard.check`
  refuses `irreversible` without a `confirmation_token` minted by `ConfirmTask`.
  Tools raise `ToolError(msg)` for user-facing failures (the LLM sees it); any
  other exception is hidden by the framework.
- Context summary across handoffs happens in `TenantAgent.on_enter` (handoff
  does not copy history), reading `tc.prev_agent.chat_ctx`.
- Event log is append-only with a per-session `seq`; the stage is appended
  **during** the call (SIGKILL-safe), not only in `on_session_end`.
  `on_session_end` persists `ctx.make_session_report()`.
- Sessions are **re-engaged**, not resumed: a dropped call is a new room and job;
  we snapshot `ChatContext.to_dict()` + stage keyed by `sip.phoneNumber` and
  rehydrate on the next inbound within N minutes.
- Prompt caching: `anthropic.LLM(model="claude-haiku-4-5", caching="ephemeral")`.
  **Haiku 4.5 only caches prefixes >= 4096 tokens** (silent no-op below; Sonnet 5
  caches at 1024). Every project prefix (system + tools + a stable policy/FAQ
  block) must exceed 4096 tokens; assert `prompt_cached_tokens > 0` on turn 2 in
  tests. Never put timestamps or per-request ids in the system prompt; never
  reorder tools. `preemptive_generation` is DISABLED (human's decision 2026-08-31: with semantic
  end-of-turn at ~0.33s, speculation never hid Haiku's ttft and only spent calls) —
  generation starts on confirmed end of turn. Sonnet 5 is the
  measured alternative in evals, not a default.
- Call `sanitize_tool_pairing(chat_ctx)` before every generation (orphan
  `tool_use` bricks the conversation with Anthropic 400s).
- STT: Soniox `stt-rt-v5`, `language_hints=["es","en"]`, endpointing
  `level=2 / sensitivity=0.3 / max_endpoint_delay_ms≈1000`, `context=` (Soniox
  silently ignores `keyterms`). Keep `sample_rate=16000` even on PSTN.
  The provider is a slot (`Project.stt_provider`, overridable from the console):
  the alternative is Deepgram Flux `flux-general-multi` via the plugin's `STTv2`
  (`/v2/listen`) — never `flux-general-en`, which 400s on a `language_hint`.
- Every transcript passes `core.stt_gate` in `TenantAgent.stt_node`: a streaming
  STT hallucinates over comfort noise (real call AJ_rt86KogpPxDa: a final
  "Thank you." into an empty line), so a final with no voiced audio behind it in
  the last 2.5 s is refused and logged as `stt.phantom`. Never a phrase
  blocklist — the invention changes every time. Thresholds are project data
  (`Project.stt_gate`). Overriding `stt_node` forfeits the framework's
  STT-pipeline reuse across a handoff; that price is paid knowingly.
- TTS: ElevenLabs `eleven_v3_conversational` (primary) / `eleven_flash_v2_5`
  (latency profile), `sync_alignment=True`. Never `eleven_turbo_v2_5`
  (deprecated) and never `eleven_v3` (non-realtime). On interruption the
  plugin closes the context; do not flush.
- VAD `inference.VAD(model="silero")`, turn detector `inference.TurnDetector()`
  (v1-mini, local, CPU). VAD `min_silence_duration >= 0.25` or the session
  raises. No GPU anywhere.
- Chat mode: `RoomOptions(audio_input=False, audio_output=False)`; agent text
  arrives on `lk.transcription` as deltas, user text goes on `lk.chat`. Client
  distinguishes speaker by `participantInfo.identity`, not by track id.
- DeepEval: never leave `@observe(metrics=[...])` in production code; mark
  voice test cases `flaky=True`; hard policies use `ConversationalDAGMetric`,
  not `GEval`; eval rooms are created by `api.py` with dispatch metadata (the
  `LiveKitConnector` cannot pass metadata).
- Ring 4 (`core/scoring/`) scores every finished call from `api.py`, never from
  the job process: four checks decided by code, then AT MOST one Haiku call,
  whose worst case is priced against `SCORING_CAP_EUR` BEFORE it is made and
  skipped under three turns. The verdict is `session.score`, one more
  append-only log line at `max(seq)+1`. `Project.scoring=False` opts a project
  out; `SCORING_SWEEP=0` opts a deploy out.
- Secrets only from env. Never commit `.env*` except `.env.example`.

## Layout

```
worker.py  api.py  pyproject.toml  Dockerfile  CLAUDE.md  REPORT.md
core/        runtime: context, contracts, registry, routes, router, session, providers, auth, control_plane,
             agents/ tools/ adapters/ state/ observability/ security/ testing/
tenants/     _template/, clinica-norte/, tienda-sur/ — tenant.py, adapters/, projects/<p>/{project,agents,tools,prompts}.py, evals/
tenant-sdk/  TS client for remote tools (outbound WS)
client/      web client (livekit-client): voice + chat
ui/          React app (switcher, conversation, call log, sessions, evals, supervisor)
infra/       compose/ (livekit, sip, redis, minio, caddy), migrations/
presentation/ self-narrating deck (stage engine) + static/PDF export
tests/       unit + evals (ring 1); tenants/*/projects/*/evals/ hold per-project goldens
tmp/         ignored: research docs, recordings
```

## Commands

```
uv sync                                  # deps
python worker.py console                 # talk to the agent in the terminal (key toggles text/mic), --record saves OGG
python worker.py console --tenant tienda-sur
python worker.py dev                     # against a LiveKit server (LIVEKIT_URL/API_KEY/API_SECRET)
python -m convo sessions list|show <id>  # read a session's event log (not `platform`: it shadows the stdlib module)
pytest -m unit                           # ring 1 (fast)
deepeval test run tests/evals -n 4       # ring 1 metrics; tenants/*/evals for per-project goldens
docker compose -f infra/compose/dev.yml up   # livekit-server --dev + redis (ms-8+)
```

## Working on the board (taskops)

- This session's MCP server may be pinned to another repo: pass
  `repo_path=/Users/berna/prueba-abai` on every taskops call.
- Orchestrator plans (`taskops_plan`), assigns (`taskops_assign`), spawns one
  Opus sub-agent per brief, reviews in-session (`taskops_review`) and merges
  (`taskops_merge`). Never raw git merges in the shared checkout; never
  `git switch`. Workers pass `actor=agent:<dev>/<name>` on every call.
- Cards are small (one afternoon) and every milestone ends with a command the
  human runs to see the result. Seams first (serialized), then parallel cards.
- Commits: `Bernardo Castro <me@bernardocastro.dev>`, no `Co-Authored-By`, no
  generated-with trailers. Versions and tags are the human's call.

## Every milestone ships four things (non-negotiable)

1. **A command the human runs** to see it working (`console`, a CLI, a URL).
2. **`.taskops/reports/ms-N.md`** — a learning report, not a usage sheet: what we
   set out to do, what we achieved, what we learned the hard way (with the real
   cause), the decisions and why, where the project stands, what comes next.
   Written so a person or an agent picking the project up cold understands how
   we got here. Index in `.taskops/reports/README.md`. How-to lives in README,
   design in REPORT.md, generated artifacts (DeepEval HTML, recordings) in `tmp/`.
   After the commit that carries a report, register it on the board with
   `taskops_filed path=.taskops/reports/ms-N.md title=… sha=<commit> milestone=ms-…`
   — a report that is not filed does not exist for the board.
3. **DeepEval, incrementally** — even one metric. Prompts must keep a consistent
   line milestone to milestone: per-project `goldens.json` grows with every card,
   `deepeval test run` is part of the milestone's definition of done, and the
   HTML report links the DeepEval HTML output.
4. **An nvim command** in the closing note of every card to read the code:
   `nvim -p core/x.py core/y.py tenants/…` — the human is a code judge too.

Core before UI: the core must be tested (unit + evals + real calls through
Twilio) before any UI work starts. CLI before UI.

## Code style — Rails-clear

- Public methods first and visible; private helpers below, prefixed `_`.
- One blank line between methods, two between classes; nothing glued together.
- Every public method has a one-line docstring saying what it does for whom.
  Tool docstrings are the schema the LLM sees — write them for the model.
- One domain per module, one responsibility per class; files stay small
  (soft limit ~300 lines, never near 1000). Split before it grows.
- Explicit over clever: no metaprogramming, no hidden globals, no magic
  imports. A reader should follow a request end-to-end by opening files in order.
- Python 3.12, `ruff` (line 100), full type hints; dataclasses for internal
  data, pydantic for anything crossing a process boundary.
- Tests: `pytestmark = pytest.mark.unit` or `.evals` per module; one behaviour
  per test; names read as sentences.
- Open-source mindset in every card: each card's spec says what a stranger
  could reuse from it and what would need a contribution upstream.

## Voice

Default TTS voice: ElevenLabs `Carolina - Spanish woman - es_ES`
(`UOIqAnmS11Reiei1Ytkc`), peninsular, conversational. Alternatives in the
account: `Carolina Ruiz` (`h2cd3gvcqTp3m65Dysk7`), `Sara Martin - 3`
(`gD1IexrzCvsXPHUuT0s3`). Voice is per-project data, never hardcoded in core.
