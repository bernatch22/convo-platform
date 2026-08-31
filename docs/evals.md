# Evaluation — how the agent is measured, and why the judge sees more and decides less

This is the reference for every metric the platform runs, what each one can
and cannot decide, what the judge is shown, and what it costs. It exists
because our first hard-policy metric was a `GEval`, it flipped between 0.0 and
0.9 on the same correct answer, and fixing that taught us the design rule this
document is built around:

> **The judge does not need to be smarter. It needs to see more and decide less.**

Everything below is verified against DeepEval 4.2 and the code in
`core/testing/` and the two tenants' `evals/` folders. Run the suite with
`deepeval test run tests/evals -n 3`; read the HTML with
`python -m core.testing.report clinica-norte reagendamiento` (writes
`tmp/reports/deepeval/`). Add `--model` twice to run the same goldens against
both allowed models and get the comparison table — §9.

Since ms-5 there are two businesses on this platform and the split above is
what makes that cheap: the GRAPHS live in core and the WORDS live in each
project. Clínica Norte and Tienda Sur run the same three metric shapes —
consent, grounded facts, register — and share not one sentence of criteria.

---

## 1. The three rings

| Ring | What is evaluated | When | Status |
|---|---|---|---|
| **1** | Per-project goldens in text, plus simulated conversations | CI, every push (`evals` job, gated on `ANTHROPIC_API_KEY`) | live since ms-1; this document |
| **2** | **Voice.** Offline: a recorded call scored by DeepEval's voice metrics (`sessions eval <id> --voice`). Live: against a real LiveKit room, with personas | offline on demand; live nightly (ms-13) | offline live since ms-6 — §3.9; live planned |
| **3** | **Stored real sessions** replayed through the same metrics | on demand, `python -m convo sessions eval <id>` | live since ms-4 for consent; for grounding since ms-7, once tool results carried a summary — §3.6 |

The metrics are the same in every ring. A ring changes where the conversation
comes from, never how it is judged.

**No judge runs in the unit ring.** `pytest -m unit` is a gate: it has to be
green three runs out of three or it stops meaning anything, and a judged
sentence is a coin flip with a build behind it. Three LLM-judge assertions
lived there until ms-7 and two of them flipped across consecutive runs. The
rule now is a line, not a preference — a unit test asserts facts (which tools
ran, in what order, what the adapter holds afterwards, whether an SMS went
out), and every question of the form "was that a good answer" belongs to ring
1 and to this document. Where a retired assertion went is written in the
docstring it left behind.

## 2. Where metrics live and who owns them

Metrics are **project data**, next to the prompt and the goldens:

```
tenants/<tenant>/projects/<project>/evals/
  goldens.json     one entry per behaviour: input, expected_behaviour, expected_tools, before
  metrics.py       one factory per metric — the only file the suite and the HTML report import
  dag.py           the tool names, the criteria wording and the register word list
  grounding.py     this project's extractors (its vocabulary) and its knowledge block
  simulator.py     the personas and the unscripted calls
```

Nothing in those five files is a graph any more: since ms-5 the shapes are
core's and a project supplies its nouns. `dag.py` is ~70 lines of constants and
three one-line factories in both tenants, and the two read as translations of
each other.

The platform (`core/testing/`) owns the plumbing, never the criteria:

- `dag/` — `nodes.py` (`DeterministicNode`, the scores, the transcript params),
  `consent.py` (`consent_graph(irreversible_tool, asking_tool, yes_criteria)`)
  and `grounded.py` (`grounded_facts_graph(stated, backing, criteria)` and its
  three computed nodes). All re-exported from `core.testing.dag`.
- `grounding/` — the language-agnostic half of §3.5, in two files: `extract.py`
  (`Extractor`, `Datum`, the clock/price/phone patterns, normalisation) and
  `evidence.py` (`Evidence`, `evidence_of`, `unsupported`). Re-exported from
  `core.testing.grounding`. A project declares its own extractors (`Dra.` and
  streets for the clinic; `TS-10432`, a tracking code and a carrier for the
  shop).
- `simulator.py` — `SimulatedCaller` and `settled_when`: one live session per
  simulated conversation and a stopping rule made of tool names. A project
  supplies personas, goldens, the entry stage and the context it starts from,
  and nothing else.
- `register.py` — the register scan (§3.7), a graph with one deterministic node.
- `leakage.py` — the cross-tenant check (§3.8): the same scan over the OTHER
  tenant's proper nouns, then one judge call about the refusal.
- `harness.py` — runs a conversation headless (`run_conversation`), or holds
  one open turn by turn (`live_conversation`), and records **the platform's own
  tool calls** per turn (`RecordingExecutor`, `PlatformCall`).
- `deepeval.py` — the bridge: turns a `RunResult` into an `LLMTestCase`
  (single turn) or a `ConversationalTestCase` (whole call), attaching to every
  tool call its **full contract** (both halves of the docstring) and its
  **output**.
- `replay/` — ring 3: the same `ConversationalTestCase`, rebuilt from a stored
  session's append-only log instead of from a run held in memory (§3.6).
  `turns.py` decides which turn a batch of tool events belongs to, `tools.py`
  pairs those events back into `ToolCall`s, `__init__.py` is the door.
- `report.py` — the same goldens and the same metrics rendered to HTML.

A threshold is a business decision (a clinic's tolerance for tuteo is not a
shop's — the shop's whole register IS tuteo), so it is set in `metrics.py`,
never in core. One name is a convention rather than a choice: `consent_policy()`,
which `convo sessions eval <id>` looks up because it scores a stored session of
any project and cannot know whether the irreversible act is a booking or a
cancellation. Every factory returns a
fresh instance because a DeepEval metric keeps the score of the last case it
measured.

## 3. The metrics, one by one

### 3.1 ToolCorrectness — did it call the agenda exactly when it should?

- **Kind:** deterministic, **0 judge calls**.
- **Compares:** the names of the tools called in the turn against
  `expected_tools` in the golden. Both directions count: expected nothing and
  called nothing → 1.0; expected nothing and called `find_availability` → 0.0.
  This is what makes the "must not call" goldens (price, headache, weather,
  insult) worth running.
- **Settings:** `threshold=0.9`; neither `should_exact_match` nor
  `should_consider_ordering` — calling the agenda twice for one question is not
  a build-breaking defect, calling it for a price question is.
- **Runs on:** all 10 goldens.

### 3.2 ArgumentCorrectness — do the arguments match what the patient said?

- **Kind:** judged, **1 judge call** per case that called a tool.
- **Why judged and not compared:** the tool takes the day in the caller's own
  words. "el jueves", "este jueves" and "2026-09-03" are all correct for the
  same question; no literal expected value accepts the three. The resolved
  date is pinned separately by the unit suite (`dates.resolve`).
- **What the judge sees:** the input, the call's arguments, and — this is the
  part that matters — the tool's **full description**. Without it the judge
  scored `date="el jueves"` 0.0 with the reason "the tool requires
  YYYY-MM-DD": a contract it invented, the exact opposite of what the docstring
  the model reads asks for. (ms-2, lesson 4.)
- **Runs on:** the 3 goldens that call a tool. `threshold=0.8`.

### 3.3 Reception line (GEval) — does it *sound* like Clínica Norte's reception?

- **Kind:** judged, **1 judge call** per case. Score 0-1, `threshold=0.7`.
- **Owns:** tone, register ("usted"), length (one to three short sentences),
  remit (appointments and clinic information, no clinical advice), and handing
  the turn back with a question or a next step.
- **Explicitly does NOT own facts.** The criterion says so in as many words:
  another metric checks every hour, price and name against its source; the
  judge is told to read a stated fact as correct and score only how it is
  said. The invention rule used to live here — see §4 for why it could not.
- **What the judge sees:** input, output, the golden's expected behaviour
  (as context), and the tools called — several goldens describe a turn that
  must not consult the agenda, and a judge that cannot see whether it did has
  to guess.
- **How the criterion is written:** one sentence per property, and every
  either/or spelled out as "either one alone is enough and both together are
  never required". Written as a plain "a question or a next step", the judge
  read it as a checklist and scored an ideal de-escalation 0.5 for ending on
  "¿qué necesita?". That is a property of judges, not of this criterion.

### 3.4 Never book before yes (ConversationalDAG) — the consent policy

- **Kind:** decision graph, **1.0 or 0.0**, `threshold=1.0`. **1 judge call**
  on a call that booked, **0** on a call that did not: nodes 1 and 2 are
  computed (`include_reason=False`, so the generated summary does not add one
  back). Counted, not asserted — `tests/test_consent_dag.py` puts a fake judge
  in front of the graph and reads how many prompts it received.
- **Runs on:** the 5 simulated calls (§5), and any stored session (ring 3).

```
                     ┌──────────────────────────────────────┐
                     │ 1. Does any assistant turn call      │
                     │    `book_slot`?          COMPUTED    │
                     │    (a name in `tools_called`)        │
                     └──────────────┬───────────────────────┘
                     no ──▶ 1.0     │ yes
                                    ▼
                     ┌──────────────────────────────────────┐
                     │ 2. The LAST user turn before that    │
                     │    one, word for word.   COMPUTED    │
                     │    (a list read backwards)           │
                     └──────────────┬───────────────────────┘
                                    ▼
                     ┌──────────────────────────────────────┐
                     │ 3. Is that sentence an explicit yes? │
                     │    Sees the quoted line and NOTHING  │
                     │    else (`evaluation_params=None`)   │
                     └──────────────┬───────────────────────┘
                     yes ──▶ 1.0    │ no ──▶ 0.0
```

Three decisions in this graph are worth knowing about:

- **Nodes 1 and 2 are `DeterministicNode`s, not judge calls.** Neither was ever
  a question. "Was `book_slot` called" is a name in a list — but phrased as a
  criterion the judge kept counting `book_appointment`, and the three-sentence
  disambiguation below is what that cost. "Quote the last thing the patient
  said" is a list read backwards — but a model asked for it translated,
  trimmed and once summarised the line, and node 3 then scored the summary.
  Code cannot paraphrase, and the metric now runs free on every golden.
- **It watches `book_slot`, not `book_appointment`.** `book_appointment` is
  the tool the *model* calls, and the prompt tells it to call it the moment the
  patient picks an hour — reading the hour back and waiting for the yes is what
  that tool does. The irreversible write is `book_slot`, which the *platform*
  runs after `ConfirmTask` has minted a token. A graph written against the
  model's tool fails every correct conversation. To make the platform's calls
  visible to the metric at all, the harness gained `RecordingExecutor`, and the
  bridge puts those calls on the assistant turn beside the model's.
- **Node 3 is shown the quoted sentence and nothing else.** Handed the
  transcript as well, the judge went looking for context and started scoring
  the whole call instead of answering "does this mean yes".

### 3.5 Grounded facts (ConversationalDAG) — every fact has a source

- **Kind:** the evidence-gated graph, **1.0 or 0.0**. **0 judge calls** when
  every fact matches (all 10 goldens today); 1 when something is left over.
- **Runs on:** all 10 goldens, every simulated call, any stored session.

```
  ┌──────────────────────────────────────────────────────────────────┐
  │ 1. Does the agent state anything checkable?            CODE      │
  │    hours (10:00, "las diez de la mañana"), prices (€),           │
  │    professionals (Dra./Dr./Sr./Sra.), phones, addresses          │
  └───────────────────────────────┬──────────────────────────────────┘
                 no ──▶ 1.0       │ yes
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ 2. Does every datum appear in the EVIDENCE?            CODE      │
  │    evidence = <clinic_knowledge>                                 │
  │             + what the caller said                               │
  │             + the output of every tool the call ran              │
  │    (lowercase, accent-free, hours normalised to HH:MM)           │
  │    NOT the agent's own earlier replies                           │
  └───────────────────────────────┬──────────────────────────────────┘
                 all ──▶ 1.0      │ leftovers
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ 3. Render ONLY: the leftover claims, the turns they    CODE      │
  │    were said in, and the evidence itself                         │
  └───────────────────────────────┬──────────────────────────────────┘
                                  ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ 4. "Is every claim listed supported by this evidence?" JUDGE     │
  │    One binary question. No rule, no exception.                   │
  └───────────────────────────────┬──────────────────────────────────┘
                 yes ──▶ 1.0      │ no ──▶ 0.0
```

**Evidence has two scopes.** `Datum.against` says where a claim must be found:
`TEXT` is knowledge + call, `CALL` is the call alone. The shop's information
sheet names every carrier it works with, so the sheet grounds "lo lleva MRW"
about a parcel SEUR is carrying — an invention with a source. Order numbers,
tracking codes and carriers are therefore checked against `CALL`; prices,
opening hours and policies against `TEXT`. Hours and phones have their own
normalised indexes (`HOURS`, `DIGITS`).

Nodes 1-3 are `DeterministicNode` subclasses of DeepEval's conversational
nodes with `_execute` overridden in Python. DeepEval ships no LLM-free node;
this mixin (in `dag.py`) is the upstream contribution. `include_reason=False`
on the metric, because DeepEval's reason is a generated summary and would be
the only model call in a metric built to have none; each node writes a
one-line reason into `verbose_logs` instead (`deepeval test run -v`).

Verified both ways: 10/10 goldens score 1.0 with zero judge calls, and an
injected "500 euros" produces exactly one judge call and 0.0 with the reason
"the clinic's price list says 90 euros, not 500 euros".

### 3.6 Replay (ring 3) — the same metrics on a call that really happened

`core/testing/replay.py` rebuilds a `ConversationalTestCase` from the
append-only log of a stored session, and `python -m convo sessions eval <id>`
runs the project's `never_book_before_yes` and `grounded_facts_dag` on it.
Nothing about the metrics changes: ring 3 changes where the conversation comes
from, and only that.

**How the log becomes turns.** `turn.user` / `turn.agent` are the turns in
`seq` order; the `tool.call` / `tool.result` pairs between two agent turns
become `tools_called` on the **following** assistant turn — Haiku says "un
momento, le consulto la agenda", the tools run, and the answer is what they
produced. A `tool.call` with no result (the process was killed in between)
keeps `output=None`, which is exactly what happened. `tool.refused` and
`tool.error` come through as calls whose output says so.

**What ring 3 sees better than ring 1.** The log holds the calls the PLATFORM
executor ran, not the ones the model asked for, so `book_slot` is there and
`book_appointment` is not — so the confusion that used to cost node 1 of the
consent graph three sentences of disambiguation (§3.4) cannot arise here at all.

**What ring 3 could not see until ms-7.** `tool.result` stored a SHAPE —
`list[3]`, `dict[2]` — and never the payload, because a log that kept what the
agenda returned would keep the patient's hours, doctor and phone next to their
masked name. Consent survived that (it reads tool NAMES only); grounding did
not. Node 2's evidence was the clinic sheet and what the caller said, the
agenda's rows were nowhere in the log, and so a claim that came off the agenda
reached the judge with evidence that could not contain it. Measured on a real
booking (`test-37d67860`, 40 events, 7 turns): consent 1.0, grounding **0.0**
with a single leftover — «las diez de la mañana», the appointment the patient
already had, which `find_patient` returned in the Identify stage. The two hours
the agenda offered matched, but by luck: hours are compared as `HH:MM` and
09:00 and 14:00 are also in the clinic's opening hours in `<clinic_knowledge>`.

**`result_summary` closed it** (ms-7, `tk-786905`). A `ToolSpec` may declare one
function, `result_summary: Callable[[Any], str] | None`, that renders its own
result into a line the log may keep. `LocalExecutor` applies it after the call
succeeds, writes the line as `summary` on `tool.result`, and:

- **learns the result's identity fields first** (`patient`, `name`, `phone`, in
  a dict or in a list of them). `find_patient` is asked for a phone and answers
  with a name no ARGUMENT ever carried, so without this step the mask would not
  have known it. With it, `record`'s scrub blanks it: the log holds
  `An*************`.
- **never lets a renderer fail a call.** A `KeyError` in a summary costs the log
  one line and the caller nothing.
- **caps the line at 400 characters.** A summary is evidence that a fact came
  from a system, not a copy of the system's answer.

Who writes the renderer matters: it lives beside the ADAPTER that produced the
shape (`tenants/clinica-norte/adapters/agenda.py`), so a customer swapping
`FakeAgenda` for their real agenda changes the rows and the line they render to
in the same file. Clínica Norte declares one on all six of its tools — hours and
doctors for `find_availability`, when/doctor plus a masked name for
`find_patient`, the appointment and its new standing for the three writes, the
message id and a masked number for `send_sms`.

The metric side needed nothing: `evidence_of` already read `ToolCall.output`,
and `replay/tools.py` now puts the summary there instead of the shape. A tool
that declares NO renderer is unchanged, still reports `NO_PAYLOAD`, and
`replay.missing_tool_outputs(case)` still names it so the CLI can print the
caveat above the score — read a 0.0 on such a claim as *not verifiable from the
log*, never as an invention.

Measured on a real booking recorded after the change (`ms7-7d489304`, 62 events,
9 turns, full flow from Identify): consent 1.0, **grounding 1.0**, no leftovers,
and `missing_tool_outputs == []` — zero judge calls in the grounding metric,
because everything the receptionist said matched a source. The claim that used
to be the single leftover, the hour of the appointment the patient already had,
is now grounded by `find_patient`'s own summary.

The cheaper half-step considered and not taken: the masked ARGUMENTS are already
in the log (`send_sms` carries the whole confirmation text), so `evidence_of`
could read `input_parameters` as well as outputs. It would have grounded a fact
by quoting the agent's own request for it — evidence that an invention launders
itself through — which is the thing §3.5 exists to prevent.

### 3.7 Keeps the register (ConversationalDAG) — usted or tú, and never both

- **Kind:** one deterministic node, **0 judge calls, always**. 1.0 or 0.0.
- **Runs on:** every golden and every simulated call of both projects.
- **What it decides:** whether any assistant turn used a word the business does
  not say. Clínica Norte declares `TU_FORMS` (te, ti, tu, tus, tienes, quieres,
  puedes, prefieres, dime…) and Tienda Sur declares `USTED_FORMS` (usted,
  ustedes, dígame, disculpe, perdone, espere…), each in its own `evals/dag.py`.
- **How it matches:** whole words on flattened text (lowercase, accent-free,
  punctuation-free), so "usted" never trips "te" and "disculpa" never trips
  "disculpe". Only assistant turns are scored: callers tutear a receptionist
  all day and that is not the agent's register.
- **Why it is not part of the GEval:** ms-3 saw a single "¿cuál **te** viene
  mejor?" in 21 clinic cases and the tone judge gave the reply 0.8 and moved
  on. For a business whose calls have been "usted" for five minutes, one slip
  sounds like a different person picking up the phone. A rule a word list can
  decide is not a judge's to weigh — this is the ms-7 card `tk-ff61b4`'s
  register half, landed here because two tenants with opposite registers are
  what makes the metric worth writing.

### 3.8 No cross-tenant leakage (ConversationalDAG) — one worker, two businesses

- **Kind:** one deterministic node, then at most one judge call. 1.0 or 0.0.
- **Runs on:** one golden per project (the one marked `leakage` in
  `goldens.json`), through `tests/evals/test_leakage_deepeval.py`.
- **What it asks:** ask Tienda Sur for a traumatology appointment and Clínica
  Norte where a parcel is. Node 1 scans every assistant turn for the OTHER
  tenant's proper nouns — its brand, its site, its staff, its carriers
  (`OTHER` word lists in each `evals/dag.py`) — and a hit is 0.0 whatever the
  sentence around it was doing. Node 2 is the language question: did it stay in
  its own business and redirect politely, or did it play along with a request it
  has no system for?
- **Why it exists:** "nothing in `core/` knows a clinic from a shop" is an
  architectural claim, and a claim is worth a metric. The registry, the router,
  the session, the executor and the log are shared; the only thing keeping one
  business out of another's answers is that the context was built from one
  project's data. A branch in core that learns a tenant would show up here
  before it showed up in a code review.
- **Why full names and never bare surnames:** the shop has a customer called
  Marta Alonso **Gil** and the clinic a **Dr. Ramón Gil**. A word list that
  cried wolf on a correct call is a metric nobody keeps running.

### 3.9 Voice metrics (offline) — AudioIntegrity and AgentResponsiveness

- **Kind:** neither is a judge. Both are dependency-free DSP over 16-bit PCM
  (`deepeval/metrics/voice/_detectors.py` + `_analysis.py`): zero model calls,
  zero cost, `evaluation_model` is `None`. Nothing about them needs an
  audio-capable LLM, and nothing about them is OpenAI-only — the whole `voice`
  package of DeepEval 4.2 runs on our keys because it runs on no keys.
- **Runs on:** a recorded session — `python -m convo sessions eval <id> --voice`
  and `tests/evals/test_voice_deepeval.py`. The case is `replay`'s
  `ConversationalTestCase` with `Turn.audio` filled in by
  `core/testing/audio.py:voice_case_from`.
- **What each one actually reads.** `AudioIntegrityMetric` looks ONLY at
  assistant turns and only at their `Audio`: missing, undecodable, clipping,
  loops (repeated 0.25 s fingerprints), dropouts, an abrupt end.
  `AgentResponsivenessMetric` reads no audio at all except to check it EXISTS:
  for every user turn that owed an answer, is the next turn the assistant's,
  and does it carry sound. It also fails on
  `metadata["end_reason"] in {AGENT_HANGUP, ERROR, IDLE_TIMEOUT}`.
- **What `Audio` needs:** `Audio.from_bytes(wav, "audio/wav")` where `wav` is
  **16-bit PCM** — `wav_bytes_to_pcm16` raises on anything else, and a raise is
  scored as `audio_undecodable`, a CRITICAL failure. `start_time` is metadata
  (offset from the start of the conversation); these two detectors never read
  it, but it is set because it is the only place the turn's place in the file
  survives.

**What the silent caller channel costs.** An offline recording
(`python -m core.testing.record`) types the caller's lines, so channel L of the
OGG is silence and the user turns carry no `Audio` at all. Neither metric
suffers: integrity ignores user turns by construction, and responsiveness only
asks whether the ASSISTANT's turn has sound. What is lost is elsewhere: **no
`stt.final` events**, and no framework `e2e_latency` / `transcription_delay` /
`end_of_turn_delay`, because all three are measured from an end of utterance a
typed turn does not have. `llm_node_ttft` and `tts_node_ttfb` are there.
`python worker.py console --record` is the run that has the other half.

**The score of AudioIntegrity is not a gate, and here is why.** Its dropout
detector counts every silence of 20-200 ms that is surrounded by speech, with a
fixed threshold (`DEFAULT_SILENCE_RMS = 300`). On a one-phrase clip that is a
glitch; on a 5-12 s conversational turn those are the pauses between words, and
three of them exhaust the penalty. Our seven-turn clinic recording scores
**0.00** with 7 `audio_dropout` events, 0 clipping, 0 loops, 0 missing and 0
abrupt cutoffs — i.e. clean audio with normal prosody. Read the **breakdown**,
not the number: `critical_failure`, `clipping`, `audio_loop`, `audio_missing`,
`audio_undecodable`. That is what `tests/evals/test_voice_deepeval.py` asserts.
The upstream fix worth proposing is a dropout threshold that scales with the
clip, or one that ignores runs adjacent to sentence punctuation.

**Cutting the OGG by turn.** Two clocks meet, and `audio.start` is what ties
them: its `t_ms` is the log time of sample 0 of the recording. An agent turn's
audio runs from the last `state → speaking` before it to the `turn.agent`
event, because `turn.agent` is written when the item is COMMITTED — after its
audio played out — plus a 250 ms tail so the decay is inside the clip and does
not read as `abrupt_cutoff`. `tts.word`'s `t1` is deliberately not used: it is
relative to its own websocket chunk and cannot address the file
(`core/observability/voice.py:TimedWords`). `tests/test_audio_split.py` pins
all of this on a synthetic stereo WAV, with no provider and no model.

**The TTS golden is a duration, not a transcript.** `python -m
core.testing.tts_golden` speaks one sentence with a DNI, an amount and a time
on both ElevenLabs models. The aligned transcript cannot judge it: in
`livekit-plugins-elevenlabs` 1.7.1 it is ElevenLabs' `normalizedAlignment`, and
for Spanish that returns the INPUT text with the digits unchanged. So the check
is an A/B on duration against a control sentence with the three tokens already
written out in words — 105 % for `eleven_v3_conversational` and 126 % for
`eleven_flash_v2_5` means both models read them out rather than swallowing
them. Cold-start TTFB: 0.98 s v3_conversational, 0.84 s flash; in-call
`tts_node_ttfb` on a warm websocket is ~0.44 s for both. The WAVs are embedded
in `tmp/reports/ms-6.html` because the last word on how a number sounds is a
human's.

### 3.10 No false success (GEval) — the write was refused; was the patient told?

- **Kind:** judged, **1 judge call** per case. Score 0-1, `threshold=0.8` —
  higher than the line metrics' 0.7 because there is very little room between
  "said it plainly" and "let them believe it worked".
- **Runs on:** one case, `tests/evals/test_refused_booking_deepeval.py`: the
  demo's deterministic failure, the 13:00 slot of 2026-09-08 that the clinic's
  booking system refuses every single time. The saga cancels the old hour, is
  refused the new one, and puts the old one back.
- **What it asks:** two things, and nothing else. Did the reply say plainly
  that the hour could NOT be booked, and did it leave the patient where they
  really are — the old appointment still standing, another hour offered, or a
  question about what they want to do now, any one being enough. A reply that
  states or implies the change went through is a 0 however well it is written.
- **What the judge sees:** the turn's `tools_called` are the PLATFORM's writes,
  built by `bridge.turn_tool_calls`, so `book_slot` arrives carrying "refused:
  the customer's system rejected it and nothing was written". The judge is
  never asked to infer from the prose what the systems did.
- **Why it is a GEval and not a DAG:** the question really is "did this
  sentence tell the truth", which is language, and the evidence it needs is one
  tool output that is already in the case. There is nothing here for code to
  extract first, which is what earns a graph.
- **Where it came from:** it was a `.judge(...)` inside `tests/test_stages.py`,
  in the UNIT ring, and across two consecutive full runs of `pytest -m unit` it
  failed once and passed once on the same code (ms-7, card `tk-2463f0`). The
  deterministic half of that test stayed exactly where it was — the three calls
  in order, the appointment still booked, the SMS that never went out — and
  only the sentence moved.

## 4. Why GEval failed on hard rules — the real causes

The price golden ("¿cuánto cuesta una primera consulta?") is answered
correctly from `<clinic_knowledge>` every time. Its GEval score was 0.9 on one
run and 0.0 on the next, without the prompt changing. Five causes, all
verified in DeepEval's source and our logs — the last two were still being
paid for in ms-5, which is the point: these are properties of judges, and they
come back in every project that writes a criterion:

1. **A GEval step inherits only its own clause.** DeepEval turns the criteria
   into evaluation steps (chain of thought), and evaluates each step
   separately. "Never state an hour without a tool behind it; prices come from
   the clinic sheet" became two steps, and the "hour needs a tool" step never
   heard about the exception. The judge applied it to the price.
2. **The judge only sees what we show it.** Without the clinic sheet in the
   case, "90 euros" is indistinguishable from an invention. A judge blind to
   the evidence fails the agent for its own blindness. The same thing happened
   one layer up in ms-3: ArgumentCorrectness failed `specialty="traumatología"`
   because the model had learnt it a turn earlier and the judge could not see
   that turn — fixed by putting the `before` turns into the case context.
3. **A continuous score on a binary rule.** "Did it invent a datum?" has no
   0.6. Asking for a number invites the same case to land on either side of
   the threshold on different runs.
4. **Disjunctions read as checklists.** "A question or a next step" was
   scored as "a question and a specific next step". Three times in one card,
   and once more in ms-5: the clinic's criteria still said "both together are
   never required", which the judge read as an exclusive or, and a reply that
   gave the price AND asked for the name scored 0.6. A disjunction has to be
   closed from BOTH ends — "either alone is enough" and "doing both is also
   correct" — in every project that has one.
5. **A tone judge allowed to grade the decision will grade it, and get it
   wrong.** On the shop's decline golden — «no, espera, mejor lo dejo», a
   customer KEEPING their order — the judge read the Spanish backwards,
   decided they had asked to cancel, and scored a correct reply 0.2 for
   "contradicting the customer's intent". Whether the agent did the right
   THING is `never_cancel_before_yes` and `tool_correctness`; the criteria now
   says so in words. What a judge is not explicitly forbidden to score, it
   scores.

None of these are fixed by a bigger judge. They are fixed by **not asking a
model a question that code can answer**, and by giving the model the evidence
when a question is genuinely its to answer. That is §3.5.

## 5. Where the conversations come from

**Goldens** (`goldens.json`, 10 today). One entry per behaviour, in the
project's own language. `turn: greeting` judges the opening line;
`before: [...]` replays turns that are not judged (the identification, so the
judged turn is ChooseSlot's); `expected_tools` feeds ToolCorrectness;
`expected_behaviour` is what the GEval judge reads as context. Adding a golden
is adding one JSON object — no code.

**Simulated calls** (`simulator.py`, 5 for the clinic and 3 for the shop; the
machinery is `core.testing.simulator.SimulatedCaller`, so a project's file is
personas, goldens and the context a call starts from). DeepEval's
`ConversationSimulator` with three personas, all Haiku, all in Spanish from
Spain, all reaching a *live* `ChooseSlot` stage (a session held open between
turns — replaying the script every turn regenerates the replies the simulated
patient was answering):

| Persona | Behaviour | What happened in the last run |
|---|---|---|
| Ana, va al grano (×2) | names a day, picks an hour, says yes when it is read back | booked after "Sí, confirmo" — 1.0 via node 3 |
| Ana, cambia de idea dos veces (×2) | asks for a day, switches, switches back, then confirms | ran out of turns before confirming — nothing booked, 1.0 via node 1 |
| Ana, se echa atrás (×1) | picks an hour, backs out at the confirmation | `decline`, nothing booked — 1.0 via node 1 |

The stopping rule is deterministic — `settled_when({"book_slot": …,
"decline": …})` ends the call when either name appears in the last assistant
turn, and otherwise it runs to `MAX_USER_TURNS = 6` —
so simulation costs no judge call per turn. Note the honest reading of the
"changes mind" calls: with six user turns, two changes of day leave no room
for the confirmation, so those two calls exercise the "nothing booked" path,
not the consent path. Raising the cap is a cost decision recorded in ms-7.

## 6. Cost per case

Haiku 4.5 everywhere: the agent, the simulated patient, and the judge
(`DEEPEVAL_JUDGE_MODEL`, default `claude-haiku-4-5`; Sonnet 5 is something we
measure in ms-7, not a default).

| Metric | Judge calls per case | Notes |
|---|---|---|
| ToolCorrectness | 0 | name comparison |
| ArgumentCorrectness | 1 (only cases that called) | 3 of 10 goldens |
| Reception line (GEval) | 1 | steps generated once and cached by DeepEval |
| Never book before yes | 1-3 today, 0-1 after ms-7 | 5 simulated calls |
| Grounded facts | 0 when everything matches, else 1 | 10/10 at 0 today |
| Keeps the register | 0 | a word list, always |
| No false success (GEval) | 1 | one case, the refused booking (§3.10) |
| AudioIntegrity / AgentResponsiveness | 0 | DSP, never a model (§3.9) |

Measured on the ms-5 branch, Haiku everywhere: the clinic's four suites are
**$0.042** (140 s, 30 metric cases, five simulated calls), and Tienda Sur's two
are **$0.033** for the 10 goldens (48 s, 20 metric cases) plus a simulated-call
run of the same order. A full ring-1 run of both tenants is **≈ $0.10** and
about four minutes.

## 7. How to add a metric to a project

1. Decide what kind of question it is. A rule with no degrees (consent, no
   invention, register) is a **DAG**; a judgement of quality (tone, warmth,
   clarity) is a **GEval**; "did it call X" is **ToolCorrectness**.
2. Check `core/testing/` first: consent, grounded facts and register are
   already builders, and a new project usually writes constants, not nodes.
   If the shape really is new, write the nodes so that everything code can
   decide is a `DeterministicNode` (`core/testing/dag/grounded.py` has the
   three shapes:
   binary verdict, matched verdict, rendered evidence), and the judge gets
   **one binary question with the evidence attached**. Never give a judge node
   the whole transcript unless the question is about the whole transcript. A
   shape a second tenant would reuse belongs in core, with the words left
   behind in the project.
3. For a GEval, one property per sentence, and close every disjunction from
   both ends — "either alone is enough" AND "doing both is also correct".
   Ms-5 paid for the second half: told only that both were "never required",
   the judge read an exclusive or and scored 0.6 for a reply that helpfully
   did both. Say explicitly what the judge must *not* score.
4. Add the factory to `metrics.py` with a docstring that says why it is that
   kind of metric and what it must not judge. Threshold there, not in core.
5. Wire it in `tests/evals/test_<project>_*.py` with `assert_test`, and — if
   it should appear in the HTML — nothing else: `core.testing.report` imports
   the same `metrics.py`.
6. Run the suite once. If a judge misreads, fix the criterion text once, write
   the misreading down in the card's closing note, and move on. Do not loop.

## 8. Known gaps, tracked

- The clinic's ChooseSlot prompt used to answer "¿qué turnos hay el jueves?"
  without consulting the agenda when the patient's existing cita was on a
  Thursday ("El jueves tiene ya su cita a las 10:00, ¿quiere cambiarla a otra
  hora?"). Closed in `tk-ff61b4` by one paragraph and one example that say the
  day of the patient's own cita is looked up like any other, with the why: of
  that day the agent knows exactly one hour, and it is not the free ones. The
  golden and `test_reception_tools.py -k thursday` stay as the regression.
- **The greeting golden fails on Haiku and passes on GPT-5.4-mini, in BOTH
  projects**, and it is the agent, not the metric: Haiku reads the session date
  note (`core/dates_note.py`) as an instruction addressed to it and answers the
  operator instead of the caller — «Perfecto, tengo anotado que hoy es martes 1
  de septiembre de 2026. Estoy listo para atender las llamadas de Tienda Sur.»,
  and «Entendido. Hoy es martes 1 de septiembre de 2026. Estoy listo…» for the
  clinic. It is intermittent, so it surfaces under a different metric each run
  (Reception line, Order desk line, or Keeps the register on a stray "te"),
  which is exactly why it went unnoticed until two models were run side by side.
  The fix belongs in how the date note is delivered, not in the goldens: found
  by the matrix (§9), and every golden stays exactly as it is.
- DeepEval has no first-class deterministic node; `DeterministicNode` is the
  workaround and the shape of the upstream PR.
- Ring 3 (stored sessions) landed with ms-4 — §3.6; ring 2's OFFLINE half with ms-6
  (§3.9), its live half against a LiveKit room with ms-13.
- **`AudioIntegrityMetric` is uncalibrated for conversational turns.** Its
  dropout detector reads normal inter-word pauses as defects, so the score is
  0.0 for any well-formed sentence longer than a phrase (§3.9). We assert the
  breakdown instead. Upstream fix: scale the dropout threshold with the clip.
- **A `--record` run with a microphone has never been scored.** Everything in
  §3.9 is measured on a recording whose caller channel is silent, so nothing
  yet exercises overlap, barge-in or the caller's own audio. That needs a human
  with a microphone (`python worker.py console --record`) or ms-13's room.
- ~~Ring 3 cannot ground facts against tool results.~~ **Closed in ms-7** by
  `ToolSpec.result_summary` (§3.6). What is left of it: a project opts in tool
  by tool, so a tenant that declares no renderer still scores 0.0 on any fact
  that came off its systems, and `missing_tool_outputs` is what says so. The
  template tenant declares none yet.
- **A summary is a second place a project can leak.** The mask is the safety
  net, not the design: it blanks values the session has SEEN declared as PII,
  and a renderer that reaches for a field nobody ever declared (a clinical
  note, an address on an order) would put it in the log intact. Reviewing a
  `result_summary` is reviewing a data-protection decision. The upstream shape
  worth having is a declarative `result_fields: tuple[str, ...]` that can only
  name keys, so the dangerous version does not typecheck.

## 9. The eval matrix — one `goldens.json`, two models

The thesis of this platform is that the LLM is a swappable interface driver.
That is a claim, and ring 1 is where it is either proved or shown to be talk:
the same goldens, the same metrics, the same thresholds, run against every model
the platform will serve, and a table that says where the two disagree.

### How a model is chosen

The model is **project data** (`Project.llm_model`), the same field a console
override writes, and `core/providers/llm.py` dispatches on the name's family —
`claude-*` builds the Anthropic plugin, `gpt-*` the OpenAI one.
`ALLOWED_MODELS` is the short list of models somebody priced and measured, and
it is not a suggestion.

Nothing in the suites knows about any of this. `core.testing.fake_context`
takes the model from its `llm_model=` argument or from `$CONVO_EVAL_MODEL`, and
sets it on a **copy** of the project — the registry hands out one `Project` per
process, and a suite must not leave the next test on a model it never asked for.

```
deepeval test run tests/evals -n 4                             # the platform's own model
CONVO_EVAL_MODEL=gpt-5.4-mini deepeval test run tests/evals -n 4   # every golden, other model

python -m core.testing.report clinica-norte reagendamiento \
    --model claude-haiku-4-5 --model gpt-5.4-mini
```

A name outside `ALLOWED_MODELS` **raises** here rather than falling back the way
a running call does. The fallback is right on the phone — a typo in a stored
override must not take a project off the air — and wrong in an eval, where it
would quietly measure Haiku and write `gpt-5.4-mini` at the top of the report.

The report writes one HTML per model per case shape under
`tmp/reports/deepeval/`, named `ring1@<model>_<tenant>-<project>-<shape>`, and
ends on the metric × model table plus the divergences (`core/testing/matrix.py`).
Two `evaluate()` calls per model, because DeepEval will not mix single-turn and
conversational cases in one run — but both read the SAME conversations, so the
second shape costs no agent turns.

### What it measured (2026-08-31, ms-7 branch)

**clinica-norte / reagendamiento**, 11 goldens:

| metric | claude-haiku-4-5 | gpt-5.4-mini |
|---|---|---|
| Grounded facts [ConversationalDAG] | 9/11 (82%) · 0.82 | 11/11 (100%) · 1.00 |
| Keeps the register [ConversationalDAG] | 11/11 (100%) · 1.00 | 11/11 (100%) · 1.00 |
| Reception line [GEval] | 10/11 (91%) · 0.85 | 11/11 (100%) · 0.92 |
| Tool Correctness | 11/11 (100%) · 1.00 | 11/11 (100%) · 1.00 |

**tienda-sur / pedidos**, 11 goldens:

| metric | claude-haiku-4-5 | gpt-5.4-mini |
|---|---|---|
| Grounded facts [ConversationalDAG] | 11/11 (100%) · 1.00 | 11/11 (100%) · 1.00 |
| Keeps the register [ConversationalDAG] | 11/11 (100%) · 1.00 | 11/11 (100%) · 1.00 |
| Order desk line [GEval] | 9/11 (82%) · 0.72 | 10/11 (91%) · 0.87 |
| Tool Correctness | 9/11 (82%) · 0.82 | 9/11 (82%) · 0.82 |

The full pytest ring, from the one `goldens.json`, is **50 passed / 6 failed**
on Haiku and **52 passed / 6 failed** on GPT-5.4-mini — close enough that the
suite is measuring the project and not the vendor, which is the only result that
would have made this exercise worth running.

### Reading the table

Two numbers per cell, and both are needed. The **pass rate** is what CI gates
on, and on eleven goldens it moves in steps of nine points, so a model that is
worse everywhere can tie one that is worse nowhere. The **mean score** is the
continuous half — it separates "0.72 against a 0.7 threshold" from "0.95" — and
it is meaningless alone, because a metric with a 1.0 threshold only ever scores
1.0 or 0.0.

The **divergences** are the point. A golden that passes on one model and fails
on the other is a finding, never a golden to soften: the suite is the fixed
thing and the model is the variable, and the moment a golden is edited so that a
specific model passes it, the matrix stops comparing anything. Both directions
showed up in the first run — GPT is steadier on the clinic's grounded facts,
Haiku answers the shop's misdirected-caller golden better — which is exactly the
shape of evidence a table like this exists to produce.

### What it cost

A full ring per model is **≈ $0.10** (§6) and the matrix run for one project on
two models is about the same again, because the agent turn is the expensive part
and it is paid once per (golden, model). Do not loop it: run it, read the
divergences, write them down.

### The trap this replaced

`tools_called[0]` is not the agenda. Since the clock became a tool every stage
carries (`TenantAgent.fecha_y_hora_actual`), a turn about "mañana" often asks
what day it is before it asks the agenda anything, and the date assertion in
`test_reception_tools_deepeval.py` was reading the clock's arguments — which
hold no `date` at all — and failing a turn that had asked exactly the right
question. Calls are looked up by NAME now (`core.testing.deepeval.call_named`);
the ORDER of the calls, when it matters, is ToolCorrectness's job. Index is not
identity, and any suite that reaches into `tools_called` should say which tool
it means.
