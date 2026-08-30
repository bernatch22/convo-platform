# ms-1 — LLM in text: talk to Claude Haiku from the terminal

**Landed 2026-08-30 · 2 cards · master `618ba62`**

## What we set out to do

The first thing a human can try: `python worker.py console --text` opens a
terminal chat with the reception of a demo clinic, powered by Claude Haiku 4.5
with prompt caching. No speech, no server. The same `session.run()` the console
uses becomes the unit test, and DeepEval starts checking that the prompt keeps
its line.

## What we achieved

- **A conversation that works.** The receptionist of Clínica Norte greets in
  Spain Spanish, collects name and appointment, redirects a prescription request
  to a doctor's visit, quotes the cancellation policy correctly, and closes each
  turn with one question. TTFT 0.66–0.90 s per turn.
- **The runtime shape that every later milestone reuses:** `providers.py` (the
  only place that knows vendors), `session.py` (`build_session(tc)`),
  `TenantAgent` (projects never import LiveKit), `registry.py` (tenants found by
  folder, a broken one is unroutable not fatal), `router.py` (dispatch metadata
  or console fallback → `TenantContext`), and `tenants/clinica-norte` as the
  first customer plus `tenants/_template` to copy.
- **Prompt caching that actually caches:** 4,593-token prefix, 4,850 tokens
  written on turn one, 18,667 read over the next four turns.
- **Tests at two levels:** `session.run()` + `expect.is_message().judge(llm,
  intent=…)` (Haiku judges intent) and a DeepEval `GEval` "Reception line" over
  five goldens — 5/5 on the CI run.

## What we learned

- **Haiku 4.5 only caches prefixes of 4,096+ tokens.** Our first prompt (~500
  tokens) and a first knowledge block (3,940) cached nothing — silently. Real
  reception knowledge (hours, floors, doctors, test preparation, prices, FAQ)
  plus five examples took the prefix to 4,593 and caching switched on. Sonnet 5
  caches at 1,024; this floor is now an invariant in `CLAUDE.md`.
- **Prompt shape matters more than prompt volume.** Rewritten after Anthropic's
  current guidance: one-sentence role → long stable knowledge first →
  instructions that explain *why* → five `<example>`s → prose, not bullets
  (the prompt's format leaks into spoken output). "Describe success, don't
  prohibit" replaced the NEVER-lists.
- **`anthropic` SDK 1.x breaks `livekit-plugins-anthropic` 1.7** (it passes an
  `httpx.AsyncClient`; the new SDK wants `httpx2`). Pinned `anthropic<1`.
- **The default turn detector needs a VAD.** Text-only sessions pass
  `TurnHandlingOptions(turn_detection=None)`.
- **The console starts in audio mode**; without a TTS it crashes at the first
  reply. Fixed in ms-2 by switching audio off when a project has no TTS.
- **LLM-judged evals move between runs.** The greeting golden scored 0.70,
  then 0.60. The real cause was ours: the agent introduces itself in the
  opening line (`on_enter`), so when the user says "hola" it rightly does not
  introduce itself again — the golden was judging the wrong turn. Fixed in
  ms-2: greeting goldens score the opening line. Lesson kept: every eval
  failure gets read before it gets "fixed".
- **Identity-linked Anthropic keys need an `anthropic-workspace-id` header**;
  `providers.py` supports `ANTHROPIC_WORKSPACE_ID`, but a plain workspace key
  is simpler.

## Decisions

- Prompts are project data (`tenants/<t>/projects/<p>/prompts.py`,
  `knowledge.py`), never inline in `core`.
- Claude Haiku 4.5 is the default LLM; Sonnet 5 is measured in evals, not a
  default.
- Tests that call the model carry the `unit` marker but skip without
  `ANTHROPIC_API_KEY`, so the keyless CI job stays green; a second CI job runs
  them with the secret.
- Reports are learning reports (this file), not usage sheets.

## Where we stand

One tenant, one stage, no tools, no event log, no audio. A human can chat with
the receptionist from the terminal and read the judge's reasoning on five
goldens. Cost of the whole ms-1 evaluation work: cents.

## Next

ms-2: the first business tool with a contract (`ToolSpec`, guard,
`LocalExecutor`, a fake agenda adapter) and DeepEval tool-correctness goldens.
