# ms-7 — evals ring 1: judgment became cheap, and then it started catching things

**What we set out to do.** Turn the scattered DeepEval learnings of ms-3..ms-6
into a proper first ring: per-project goldens, hard policies as DAGs, HTML
reports, and `core/testing` as the one bridge from LiveKit's `RunResult` to
DeepEval's vocabulary. The chapter was deferred while the platform grew;
closing it took one afternoon of five parallel cards — after the groundwork
made each card small.

## What ring 1 became

**Verdicts, not vibes.** The policies a business would fire us over are
`ConversationalDAGMetric`s ending in 1.0 or 0.0: never book before an explicit
yes, every stated fact has a source, the register never slips into tuteo.
GEval survives only where a sliding scale is honest (the receptionist's line).

**Judge calls are a budget, and most of the graph is now free.** The consent
DAG's first two questions — did the write run? what was said before it? — are
computed from `tools_called` and the transcript (`DeterministicNode`). A call
that booked nothing costs **zero** judge calls; one that booked costs exactly
one, and that judge is handed the quoted line, not the transcript. Proven by a
fake judge that counts prompts (13 unit tests, keyless, ~10 s). The last
hidden model call — DeepEval's generated summary — died with
`include_reason=False`; the node chain is the readable why now.

**The unit ring is deterministic again.** Five LLM-judge assertions (the card
said three; grep said five) left the unit ring — four retired into goldens
that already carried the same intent, one moved properly with the platform's
own refused-write in evidence. `pytest -m unit` passes three times in a row,
by test.

**Tool results ground facts without leaking.** Every tool can render its own
result into a PII-filtered summary beside the adapter that produced the shape;
the executor learns PII **by value** from the result's identity fields, so the
name `find_patient` answered with is masked even inside an SMS body no
argument ever carried. Grounding on a real recorded booking went 0.0-with-
leftovers → 1.0-every-fact-matched.

**The model is a slot the evals can turn.** The same goldens judge Haiku and
gpt-5.4-mini from one `goldens.json` — the harness **raises** on a model
outside the allow-list rather than falling back, because a fallback would
title a Haiku report "gpt". The matrix (metric × model, read off DeepEval's
own MetricData) lives in `docs/evals.md` §9: clinic 11/11 grounded on gpt vs
9/11 on Haiku, register 11/11 on both, tools 11/11 both.

## What it caught — the reason evals exist

1. **The Thursday defect.** «¿qué turnos hay el jueves?» when the patient's
   own cita is on Thursday: the agent answered from the cita instead of
   consulting the agenda. Fixed in the ChooseSlot prompt (a day the patient
   names is ALWAYS a `find_availability` call); the pre-landing run on the box
   shows the red, the post-landing run is the regression proof.
2. **The dates-note defect** — found only because two models ran side by side:
   Haiku, intermittently, in both projects, ANSWERS the session-date note as
   if an operator had spoken («Perfecto, tengo anotado que hoy es martes…»)
   instead of greeting. gpt never does. Filed as tk-097125; the fix is in how
   the note is delivered, not in a golden.
3. **The implicit-yes booking.** A live grounding run caught the agent booking
   after «la de las dos me viene bien» — acceptance, but not the explicit yes
   the policy demands. The simulated-conversation suite regenerates its
   dialogues each run; this nondeterminism is the feature.
4. **The clock-index trap.** Giving every agent a clock tool silently made
   `tools_called[0]` sometimes the clock; suites now select calls by name
   (`call_named`), never by index.

## What it cost

A full ring-1 run is ~$0.10 per model per project (~180 s). The deterministic
share keeps growing: consent and register cost zero judge calls on the happy
path, grounding pays one judge only for leftovers. The refused-booking suite
runs at ~$0.003. Numbers per suite in `docs/evals.md`.

## Where evals stand across rings

Ring 1 (this chapter): text, headless, per-golden — green and cheap, in CI
and launchable from the console (ms-14's screen, with per-metric diffs).
Ring 2 (ms-13, in flight): synthetic callers over real audio — the seam is
landed (rooms minted by api.py, `converse()` returns transcripts with
latencies), personas apurado and spanglish being built now. Ring 3 (every
call scores itself, tk-64bc22): planned, hooks exist in the session report.

**Honest gaps.** The milestone's original criteria asked for 20 goldens per
project (we hold 11 per suite per project), 5 simulated conversations per
project (grounding holds 5 for the clinic, 3 for the shop), and a
`reports/ms-7.html` hub (the HTML reports exist per run under
`tmp/reports/deepeval/` and in the console; no hub page was built). The
substance — policies as cheap verdicts, a matrix, catches with real causes —
is what the chapter was for.

Read the code: `nvim -p core/testing/dag/consent.py core/testing/matrix.py
core/tools/executor.py tests/test_consent_dag.py docs/evals.md`
