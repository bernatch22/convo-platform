# Evaluation — how the agent is measured, and why the judge sees more and decides less

This is the reference for every metric the platform runs, what each one can
and cannot decide, what the judge is shown, and what it costs. It exists
because our first hard-policy metric was a `GEval`, it flipped between 0.0 and
0.9 on the same correct answer, and fixing that taught us the design rule this
document is built around:

> **The judge does not need to be smarter. It needs to see more and decide less.**

Everything below is verified against DeepEval 4.2 and the code in
`core/testing/` and `tenants/clinica-norte/projects/reagendamiento/evals/`.
Run the suite with `deepeval test run tests/evals -n 3`; read the HTML with
`python -m core.testing.report clinica-norte reagendamiento` (writes
`tmp/reports/deepeval/`).

---

## 1. The three rings

| Ring | What is evaluated | When | Status |
|---|---|---|---|
| **1** | Per-project goldens in text, plus simulated conversations | CI, every push (`evals` job, gated on `ANTHROPIC_API_KEY`) | live since ms-1; this document |
| **2** | Voice conversations against a real LiveKit room, with personas | nightly (ms-13) | planned |
| **3** | **Stored real sessions** replayed through the same metrics | on demand, `python -m convo sessions eval <id>` | live since ms-4 for consent; grounding is blind to tool results — §3.6 |

The metrics are the same in every ring. A ring changes where the conversation
comes from, never how it is judged.

## 2. Where metrics live and who owns them

Metrics are **project data**, next to the prompt and the goldens:

```
tenants/clinica-norte/projects/reagendamiento/evals/
  goldens.json     one entry per behaviour: input, expected_behaviour, expected_tools, before
  metrics.py       one factory per metric — the only file the suite and the HTML report import
  dag.py           the two hard policies as decision graphs (+ DeterministicNode)
  grounding.py     pure functions: which facts a reply states, what evidence backs them
  simulator.py     three personas, five unscripted calls
```

The platform (`core/testing/`) owns the plumbing, never the criteria:

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
shop's), so it is set in `metrics.py`, never in core. Every factory returns a
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

## 4. Why GEval failed on hard rules — the real causes

The price golden ("¿cuánto cuesta una primera consulta?") is answered
correctly from `<clinic_knowledge>` every time. Its GEval score was 0.9 on one
run and 0.0 on the next, without the prompt changing. Four causes, all
verified in DeepEval's source and our logs:

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
   scored as "a question and a specific next step". Three times in one card.

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

**Simulated calls** (`simulator.py`, 5 today). DeepEval's
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

A full ring-1 run (`deepeval test run tests/evals -n 3`) is **≈ $0.04-0.05**
and about two minutes; the five simulated calls are most of it.

## 7. How to add a metric to a project

1. Decide what kind of question it is. A rule with no degrees (consent, no
   invention, register) is a **DAG**; a judgement of quality (tone, warmth,
   clarity) is a **GEval**; "did it call X" is **ToolCorrectness**.
2. For a DAG, write the nodes so that everything code can decide is a
   `DeterministicNode` (`dag.py` has the three shapes: binary verdict, matched
   verdict, rendered evidence), and the judge gets **one binary question with
   the evidence attached**. Never give a judge node the whole transcript unless
   the question is about the whole transcript.
3. For a GEval, one property per sentence, no disjunctions without "either
   alone is enough", and say explicitly what the judge must *not* score.
4. Add the factory to `metrics.py` with a docstring that says why it is that
   kind of metric and what it must not judge. Threshold there, not in core.
5. Wire it in `tests/evals/test_<project>_*.py` with `assert_test`, and — if
   it should appear in the HTML — nothing else: `core.testing.report` imports
   the same `metrics.py`.
6. Run the suite once. If a judge misreads, fix the criterion text once, write
   the misreading down in the card's closing note, and move on. Do not loop.

## 8. Known gaps, tracked

- Consent DAG nodes 1-2 are still judge `TaskNode`s; both are extractable in
  code (ms-7, `tk-ff61b4`).
- An intermittent tuteo ("¿Cuál **te** viene mejor?") appeared once in 21
  cases in ms-3. The judge was right. It is an agent defect, not a metric one:
  the prompt is hardened and a deterministic register node is added in the
  same ms-7 card.
- DeepEval has no first-class deterministic node; `DeterministicNode` is the
  workaround and the shape of the upstream PR.
- Ring 3 (stored sessions) landed with ms-4 — §3.6; ring 2 (voice) with ms-13.
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
