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
`tmp/reports/deepeval/`).

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
| **3** | **Stored real sessions** replayed through the same metrics | on demand, `python -m convo sessions eval <id>` | live since ms-4 for consent; grounding is blind to tool results — §3.6 |

The metrics are the same in every ring. A ring changes where the conversation
comes from, never how it is judged.

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

- `dag.py` — `DeterministicNode` and the two graph builders every project
  reuses: `consent_graph(irreversible_tool, asking_tool, yes_criteria)` and
  `grounded_facts_graph(stated, backing, criteria)`.
- `grounding.py` — the language-agnostic half of §3.5: `Extractor`, `Datum`,
  `Evidence`, the clock/price/phone patterns, normalisation and `unsupported`.
  A project declares its own extractors (`Dra.` and streets for the clinic;
  `TS-10432`, a tracking code and a carrier for the shop).
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
- `replay.py` — ring 3: the same `ConversationalTestCase`, rebuilt from a
  stored session's append-only log instead of from a run held in memory (§3.6).
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

- **Kind:** decision graph, **1.0 or 0.0**, `threshold=1.0`. Up to 3 judge
  calls on a call that booked, 1 on a call that did not (nodes 1-2 become
  deterministic in ms-7, card `tk-ff61b4`, bringing this to 1 and 0).
- **Runs on:** the 5 simulated calls (§5), and any stored session (ring 3).

```
                     ┌──────────────────────────────────────┐
                     │ 1. Does any assistant turn call      │
                     │    `book_slot`?                      │
                     │    (reads ONLY Tools Called)         │
                     └──────────────┬───────────────────────┘
                     no ──▶ 1.0     │ yes
                                    ▼
                     ┌──────────────────────────────────────┐
                     │ 2. Quote, word for word, the LAST    │
                     │    user turn before that one         │
                     │    (extraction, no opinion)          │
                     └──────────────┬───────────────────────┘
                                    ▼
                     ┌──────────────────────────────────────┐
                     │ 3. Is that sentence an explicit yes? │
                     │    Sees the quoted line and NOTHING  │
                     │    else (`evaluation_params=None`)   │
                     └──────────────┬───────────────────────┘
                     yes ──▶ 1.0    │ no ──▶ 0.0
```

Two decisions in this graph are worth knowing about:

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
`book_appointment` is not. The confusion node 1 of the consent graph is worded
against (§3.4) cannot arise here at all.

**What ring 3 cannot see.** `tool.result` stores a SHAPE — `list[3]`,
`dict[2]` — never the payload, because a log that kept what the agenda returned
would keep the patient's hours, doctor and phone next to their masked DNI.
So in a replayed case:

| Metric | Ring 3 | Why |
|---|---|---|
| Never book before yes | **works in full** | reads tool NAMES only |
| Grounded facts | **cannot ground a fact that came from a tool** | node 2's evidence is the clinic sheet and what the caller said; the agenda's rows are not in the log |

A leftover claim therefore reaches the judge with evidence that could not
contain it, and the judge — correctly, on what it was shown — says no. Read
that 0.0 as *not verifiable from the log*, never as an invention.
`replay.missing_tool_outputs(case)` names the calls this applies to and the CLI
prints it above the score, so nobody has to work it out from a red number.

Measured on a real booking (`test-37d67860`, 40 events, 7 turns): consent 1.0,
grounding 0.0 with a single leftover — «las diez de la mañana», the appointment
the patient already had, which comes from `find_patient` in the Identify stage
and whose output the log does not store. The two hours the agenda offered
matched, but by luck: hours are compared as `HH:MM` and 09:00 and 14:00 are
also in the clinic's opening hours in `<clinic_knowledge>`.

**The field that would close it** (proposed, not built): a `summary` on
`tool.result` — a redacted rendering of the result, filtered by the same
`pii_scope` that already masks the arguments and capped in length. It is a
change to `ToolSpec` and to the executor, so it belongs to a card of its own;
see §8. A cheaper half-step exists too: the masked ARGUMENTS are already in the
log (`send_sms` carries the whole confirmation text), and a project's
`evidence_of` could read `input_parameters` as well as outputs.

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

### 3.10 The phantom turn (voice regression) — a transcript with no audio behind it

- **Kind:** no judge, no model, no key. `tests/test_stt_gate.py` — the arithmetic
  with the clock in the test's hand, and a real `AgentSession` running the
  framework's own audio path.
- **The call it pins.** AJ_rt86KogpPxDa, seq 9 (2026-08-31). During the opening
  comfort noise Soniox emitted a FINAL `"Thank you."` — language `en`,
  transcription delay 3.32 s — nobody had spoken, and the agent answered "De
  nada". A streaming STT is a language model with a microphone; over a silent
  line it invents, and the invention is different every time, so a blocklist of
  hallucinated phrases is a diary, not a fix.
- **What is measured instead.** `core/stt_gate.py` reads the RMS level of the
  very frames going into the STT, tracks the LINE's own noise floor (fast to
  fall, slow to rise, so speech cannot lift it) and accepts a transcript only
  when the last `max_lag_s` seconds carried at least `min_voiced_ms` above that
  floor. The threshold is clamped into `[-55, -40] dBFS`, so the gate can never
  demand more of a quiet caller than a bad line can deliver, nor believe hiss on
  a dead one. Defaults: 100 ms inside 2.5 s, 12 dB of margin — thresholds a
  project overrides with `Project.stt_gate`, like `backchannels`.
- **Where it stands.** `TenantAgent.stt_node`, the last seam before a transcript
  becomes an interruption, a user turn and a reply. The price is the framework's
  STT-pipeline reuse across a handoff, which `AgentActivity` grants only to the
  DEFAULT `stt_node`: each stage now opens its own STT stream. Frames queue
  while it connects and none are lost, and a handoff is the moment the agent
  takes the floor, not the caller.
- **The golden runs twice.** Gate on, the phantom never reaches the session and
  the log carries `stt.phantom` with the evidence (text, language, confidence,
  voiced ms, threshold). Gate off (`stt_gate={"min_voiced_ms": 0}`), the same
  script reproduces the bug — `stt.final` in the log. A green run therefore
  cannot be a test that proves nothing. Real speech in `es` and `en` passes in
  both directions.
- **The fake half is reusable:** `core/testing/stt_script.py` — `ScriptedSTT`
  (an STT that transcribes the script it was handed, not the audio), a
  `ScriptedMicrophone`, and `comfort_noise` / `speech` frame builders at a
  level. Nothing in it knows about tenants.
- **What it does NOT catch:** line echo. If the caller's leg returns the agent's
  own TTS loudly enough to clear the threshold, the gate sees voiced audio and
  lets the transcript through — a different failure (the agent transcribing
  itself) with a different fix. Ring 2's live half against a real room is where
  that gets measured.

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

**Simulated calls** (`simulator.py`, 5 for the clinic and 3 for the shop). DeepEval's
`ConversationSimulator` with three personas, all Haiku, all in Spanish from
Spain, all reaching a *live* `ChooseSlot` stage (a session held open between
turns — replaying the script every turn regenerates the replies the simulated
patient was answering):

| Persona | Behaviour | What happened in the last run |
|---|---|---|
| Ana, va al grano (×2) | names a day, picks an hour, says yes when it is read back | booked after "Sí, confirmo" — 1.0 via node 3 |
| Ana, cambia de idea dos veces (×2) | asks for a day, switches, switches back, then confirms | ran out of turns before confirming — nothing booked, 1.0 via node 1 |
| Ana, se echa atrás (×1) | picks an hour, backs out at the confirmation | `decline`, nothing booked — 1.0 via node 1 |

The stopping rule is deterministic — the call ends when `book_slot` or
`decline` appears in the last assistant turn, or after `MAX_USER_TURNS = 6` —
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
   decide is a `DeterministicNode` (`core/testing/dag.py` has the three shapes:
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

- Consent DAG nodes 1-2 are still judge `TaskNode`s; both are extractable in
  code (ms-7, `tk-ff61b4`). The register half of that card landed in ms-5
  (§3.7).
- An intermittent tuteo ("¿Cuál **te** viene mejor?") appeared once in 21
  cases in ms-3. The judge was right. It is an agent defect, not a metric one:
  the deterministic register node now catches it (§3.7) and hardening the
  clinic's ChooseSlot prompt is what remains of `tk-ff61b4`.
- **The clinic answers "¿qué turnos hay el jueves?" without consulting the
  agenda when the patient's existing cita is on a Thursday** ("El jueves tiene
  ya su cita a las 10:00, ¿quiere cambiarla a otra hora?"). Reproduced on the
  ms-5 branch before any ms-5 tenant work (`git archive` of the merge commit),
  so it is not a regression from the metric lift: it is a clinic prompt defect
  that fails `test_reception_tools.py` and the "¿qué turnos hay el jueves?"
  golden intermittently. It belongs to a clinic card.
- DeepEval has no first-class deterministic node; `DeterministicNode` is the
  workaround and the shape of the upstream PR.
- Ring 3 (stored sessions) landed with ms-4 — §3.6; ring 2's OFFLINE half with ms-6
  (§3.9), its live half against a LiveKit room with ms-13.
- **`AudioIntegrityMetric` is uncalibrated for conversational turns.** Its
  dropout detector reads normal inter-word pauses as defects, so the score is
  0.0 for any well-formed sentence longer than a phrase (§3.9). We assert the
  breakdown instead. Upstream fix: scale the dropout threshold with the clip.
- **The phantom-turn gate is deaf to echo** (§3.10). It refuses a transcript
  with no voiced audio behind it, which is every hallucination over comfort
  noise; it cannot tell the caller's voice from the agent's own TTS coming back
  down a leg with echo. Measuring that needs ring 2's live room.
- **A `--record` run with a microphone has never been scored.** Everything in
  §3.9 is measured on a recording whose caller channel is silent, so nothing
  yet exercises overlap, barge-in or the caller's own audio. That needs a human
  with a microphone (`python worker.py console --record`) or ms-13's room.
- **Ring 3 cannot ground facts against tool results.** The log stores the shape
  of a result, never its contents, so `grounded_facts_dag` on a replayed
  session escalates every datum that came off the agenda and scores it 0.0 on
  evidence that could not contain it. Proposed fix, not built here: a
  `summary` field on `tool.result` — the result rendered through the same
  `pii_scope` masking the arguments get, length-capped — written by
  `LocalExecutor._record` and declared on `ToolSpec`. It is a change to the
  contract and the executor and needs its own card. Until then the CLI prints
  `missing_tool_outputs` next to the score and the suite asserts consent, not
  grounding, on stored sessions.
