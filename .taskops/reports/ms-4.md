# ms-4 — the event log: a session that tells its own story, and can be judged afterwards

**Landed 2026-08-30 · 6 cards (2 by the orchestrator, 4 by Opus workers) · lands on master with this milestone**

## What we set out to do

Make every session auditable while it is still happening: an append-only log
with a per-session `seq`, written through to disk on every fact (a process
killed mid-call leaves a log that ends where the call did), with PII masked by
the tools' own declarations, per-turn latencies, and a `session.end` that says
how it ended and what it cost. Read it from a CLI. And take the first step of
ring 3: a stored session becomes a DeepEval test case and is scored by the same
metrics that score the goldens.

## What we achieved

- **`python -m convo sessions show <id>`** prints the whole call as a `seq`
  table: `session.start` → `stage.enter` → `turn.agent ttft=0.83s` →
  `tool.call find_availability {date, specialty}` → `confirm.request` →
  `turn.user "sí, confirmo"` → `confirm.granted` → `tool.call book_slot
  {patient: An*************, phone: 60*******}` → `send_sms` → `stage.handoff`
  → `session.end {outcome: completed, cost: €0.0094}`. The log now *proves*
  the consent policy: `confirm.granted` (seq 29) precedes `book_slot` (seq 34).
- **SIGKILL-safe by construction.** `EventLog.append` writes through to
  SQLite (WAL, `synchronous=FULL`) before returning; triggers refuse UPDATE and
  DELETE on `events`. `tests/test_sigkill.py` kills the writer from inside with
  `SIGKILL` at event 30 and reads back seq 1..31, contiguous.
- **PII masked by declaration *and* by value.** `pii_scope` masks named
  arguments; the executor also learns the *values* of those arguments per
  session and masks them wherever they appear in any string — the SMS text
  reads `Clínica Norte: An*************, su cita queda…` in the log while the
  gateway still receives the real name. No global regexes; a string is PII only
  because some `ToolSpec` said so.
- **Cost per session, honestly.** `session.end` carries EUR by model, computed
  from `session.usage` with a price table; an unknown model is reported as
  `unpriced`, never as free. One three-turn booking costs **€0.008–0.009**.
- **Ring 3, first step.** `python -m convo sessions eval <id>` rebuilds a
  `ConversationalTestCase` from the log alone and runs the project's two DAGs:
  on the demo booking, *Never book before yes* **1.0** and *Grounded facts*
  **1.0** (with the blind spot printed: the log stores the shape of a tool
  result, never its contents — see "Where we stand").
- **144 unit tests** (of which SIGKILL, store, log, CLI, observers, PII and
  replay are LLM-free); **30/30 DeepEval** cases. Milestone spend ≈ $0.60,
  most of it two full unit-suite runs per worker.

## What we learned the hard way

1. **A top-level package called `platform` would have broken everything.**
   The plan said `python -m platform sessions show`. The standard library has
   a `platform` module that anthropic, httpx and pytest import; a folder with
   that name at the repo root shadows it the moment the cwd is on `sys.path`.
   The CLI is `python -m convo`. Root cause: naming by product vocabulary
   without checking the stdlib.
2. **`LLM.provider` is a hostname, not a vendor.** The Anthropic plugin returns
   the base URL's `netloc` (`api.anthropic.com`); a price table keyed on
   `"anthropic"` matched nothing and reported a real call as **€0.00** — the
   worst failure a cost line can have, because it reads as success. Prices are
   keyed on the model id, and an unknown model lands in `unpriced`.
3. **`input_tokens` is the whole prompt.** The plugin's `prompt_tokens` is
   input + cache write + cache read; summing the three rows bills the same
   prompt three times. Fresh input = `input_tokens − cached − cache_creation`.
   Pinned by a test.
4. **Observers belong where every path passes.** The spec wired them in
   `start_session`; the harness calls `session.start` directly and would have
   produced goldens with no log. They live in `build_session`, the one moment
   the worker, the console and the harness all share.
5. **The audit and the transcript are different things.** Masking by value
   deliberately does not touch `turn.*` payloads: a transcript is what was said
   (the agent greets the patient by name), and ring 3 reads it back as
   evidence. Masking it would be masking the evidence, not the audit.
6. **Learn before you mask.** A PII value seen for the first time in a call
   must already be masked in that call's own log line; learning after masking
   leaks exactly the first occurrence. Longest pattern first, so a full name is
   masked before the first name it contains; values of two characters or less
   are never patterns.
7. **Ring 3 is stronger than ring 1 for consent, and blind for facts.** The
   log holds only the *platform's* tool calls, so `book_appointment` (the
   model's tool) cannot confuse the consent graph at all. But `tool.result`
   stores a shape (`list[3]`), never the agenda's rows, so grounding cannot see
   what the tools returned; the first real replay scored 0.0 on «las diez de la
   mañana» — the appointment the patient already had, whose source
   (`find_patient`) the log had not kept. The fix is a `pii_scope`-filtered
   `summary` on `tool.result` (ms-7, `tk-786905`).
8. **`AgentSession()` needs a running loop.** A synchronous test that builds
   one raises "no current event loop" — but only when it runs before any async
   test opened one, which is why it passed alone and failed in the suite.
   Every test that builds a session is `async def`.
9. **A saga that succeeds is silent.** Three `tool.call`s the executor already
   logged; a fourth "it worked" line is noise. `saga.*` appears only on
   failure: `saga.fail`, one `saga.compensated` per undo, `saga.rolled_back`.
10. **The demo recording found a real defect.** `ConfirmTask.on_enter` used
    `generate_reply()` on a task whose own context is empty; Haiku answered
    "Disculpe, he recibido una llamada sin contenido…" instead of the question,
    and the patient had to say yes twice (seq 20–29 of the recording). The
    question is rendered by the platform, so it must be spoken verbatim with
    `session.say` — card `tk-f18663` in this milestone, fixed before landing.
11. **LLM-judge assertions do not belong in the unit ring.** Three
    judge-backed unit tests flipped between two consecutive runs. They move to
    the evals ring or lose the judged half (ms-7, `tk-2463f0`).

## Decisions

- **`convo`, not `platform`** (lesson 1). Written into CLAUDE.md.
- **Live ≡ stored.** There is no in-memory buffer between an event and its
  row; `EventLog.append` returns after the store does. The cost — one fsync per
  event — is the price of a log you can trust after a kill.
- **Kinds are dotted strings**, documented in `core/state/log.py`, not an
  enum: a reader greps a log without importing anything.
- **Costs are a dict plus one FX constant** (`core/observability/prices.py`);
  ElevenLabs and Soniox have zero rows with a TODO until ms-6 makes their units
  (characters, audio seconds) real.
- **The log never stores tool payloads.** A log that kept the agenda's rows
  would keep the patient's hours next to their masked DNI. Ring 3 grounding
  waits for a declared, filtered summary rather than for the payload.

## Where we stand

Master carries the whole text pipeline with an audit trail: stages,
confirmation token, saga, event log with `seq`, PII masked by name and value,
cost per session, a CLI to read and to judge a stored call. Voice providers are
wired on the ms-6 branch. Remaining gaps are tracked: ring-3 grounding needs
tool summaries; three unit tests still ask a judge.

Try it:

```bash
uv run python worker.py console --text      # talk, then Ctrl+C: the session is in tmp/convo.db
uv run python -m convo sessions list
uv run python -m convo sessions show <id>   # the seq table
uv run python -m convo sessions eval <id>   # both DAGs on that call (≈ 1-3 Haiku calls)
uv run pytest -m unit -q                    # 144 passed
uv run deepeval test run tests/evals -n 3   # 30 cases, ≈ $0.04
```

Read it:

```bash
nvim -p core/state/log.py core/state/store.py core/state/attach.py core/observability/observers.py core/observability/prices.py
nvim -p core/tools/guard.py core/tools/executor.py tests/test_pii.py tests/test_sigkill.py
nvim -p core/testing/replay.py convo/sessions.py tests/test_replay.py docs/evals.md
```

A real recording with the CLI output and the eval: `tmp/reports/ms-4.html`.

## What comes next

**ms-5** — one worker, two businesses: the router resolves tenant and project
from dispatch metadata, `tienda-sur` joins `clinica-norte`, the template tenant
documents what a customer copies, evals run for both. Then **ms-6**: talk to
the agent from the laptop microphone — Soniox with semantic endpointing,
ElevenLabs Carolina, VAD and the local turn detector are already wired on its
branch; the event log gains `stt.final` and `tts.word` with times.
