# ms-2 — one tool with a contract: the LLM calls a fake adapter

**Landed 2026-08-30 · 5 cards (2 by the orchestrator, 3 by Opus workers) · lands on master with this milestone**

## What we set out to do

Give the receptionist her first real capability — consulting the agenda — and,
more importantly, the shape every future tool will have: a declared contract
(`ToolSpec`), a platform veto (`guard`), a single execution path
(`LocalExecutor`) that logs with PII masked and turns every failure into a
sentence the caller can hear, and an adapter that is the customer's, not ours.
Then prove with DeepEval that the model calls the tool when it should and only
then.

## What we achieved

- **`find_availability` works end to end.** "¿qué turnos hay el jueves?" → the
  model passes the patient's own words → `dates.resolve` turns them into
  2026-09-03 against `tc.today` → `LocalExecutor` guards, times and logs →
  `FakeAgenda` answers three deterministic slots → the tool hands the model the
  two it should offer → the receptionist offers two hours with named doctors and
  asks which one. TTFT unchanged (~0.7 s); prompt 5,686 tokens, cached.
- **The tool path is framework-agnostic except one file.** `contract`, `guard`,
  `catalog`, `messages` import nothing from LiveKit; `executor.py` is the only
  seam (one import, `ToolError`). Porting to another agent runtime is one file.
- **The register comes from the project.** The four sentences a caller hears
  when a tool fails live in `Project.messages` ("usted" for the clinic); core
  ships neutral defaults.
- **Dates never enter the prompt.** `TenantContext.today` carries the day; a
  pure `dates.py` (no clock, 7 tests) reads "el jueves", "mañana", "la semana
  que viene". Putting the date in the system prompt would throw the cached
  prefix away every midnight.
- **A generic RunResult → DeepEval bridge** (`core/testing/deepeval.py`) with
  three rules, each paid for by a wrong failure; nine goldens (three must call
  the agenda, six must not) scored by `ToolCorrectness` 1.0/1.0/1.0…,
  `ArgumentCorrectness` 1.0 on the calling ones, and the "Reception line" GEval
  0.7–1.0. 54 unit tests, three DeepEval suites green, ~$0.02 per run.
- **Learning reports** replaced the usage sheets: `.taskops/reports/ms-N.md`,
  registered on the board with `taskops_filed`.
- **The console no longer crashes in audio mode** for a text-only project.

## What we learned

- **Agent tests assert on the whole turn, never on the first event.** Haiku
  says "un momento, le consulto la agenda" before calling the tool. Two tests
  written against the first event failed on correct behaviour; `final_message`
  and `skip_next_event_if` are the fixes, and the rule now lives in the harness.
- **Read the eval failure before "fixing" it.** Of the first DeepEval run's five
  failures, one was the agent's (see next), four were the eval's. Loosening the
  intents would have hidden a real defect and enshrined four blind spots.
- **The real defect the judge found:** the tool handed the model three slots and
  the prompt said "offer two", so the model read three hours and asked "¿cuál de
  las dos primeras?". Fixed where the decision belongs — the tool hands over
  exactly two and says the day has more — not by rewording the intent.
- **A judge without the tool's schema invents one.** `ArgumentCorrectness`
  scored `date="el jueves"` 0.0 because it decided the tool "requires
  YYYY-MM-DD" — the opposite of the docstring the model reads. LiveKit splits a
  docstring in two (prose → description, `Args:` → JSON schema); the judge must
  see both halves. The bridge now attaches the full contract and the tool's
  output; scores went 0.0 → 1.0 and stayed.
- **A judge without the tool's output calls real hours "invented".** Same cure:
  `TOOLS_CALLED` is an evaluation param and each `ToolCall` carries its output.
- **A GEval step inherits only its own clause.** DeepEval decomposes a criterion
  into evaluation steps; a rule and its exception written in two sentences
  became two steps, and the "hours need a tool" step had never heard that
  prices come from the clinic sheet. Rule and exception go in one sentence.
  Even so, the price golden's GEval still flips between 0.0 and 0.9 across
  runs — the follow-up (ms-7) moves "no invention" to a deterministic
  `ConversationalDAGMetric`; hard policies do not belong in a GEval.
- **Judges read "A or B" as "A and B".** Three times in one card ("ends with a
  question or a next step", "any of these four steps"). Write disjunctions as
  "either one alone is enough; both are never required".
- **An example outranks an instruction when they disagree.** A leftover
  `<example>` from ms-1 (ask the name first) made Haiku ask for the name when the
  patient had already named a day, despite a rule saying the opposite. Examples
  are the strongest signal in a prompt — keep them current or they teach the old
  behaviour.
- **Greeting made deterministic:** "Clínica Norte, buenos días, le atiende
  recepción. ¿En qué puedo ayudarle?" 5/5 runs, after telling the model the
  three things the opening line does at once and why.
- **On the board:** a card closed with `no_code` before being assigned has no
  branch and cannot be merged (planning cards get a commit or are closed after
  landing); zsh `noclobber` bit twice more before `setopt clobber` became the
  first token of every command.

## Decisions

- Tools are declared, guarded and executed through `tc.tools.call()`; an Agent
  never touches an adapter.
- How many options a caller can hold is a project decision made once in the
  tool, not arithmetic the model repeats every turn.
- `ToolRefused` (platform veto) is distinct from `ToolError` (what the model
  hears); ms-3's `ConfirmTask` decides what to say when the guard refuses.
- Metrics are project data (`evals/metrics.py`), like prompts and goldens.
- Reviews stay in session: two of three worker cards went back once, one twice;
  every return was a test that judged the wrong thing, none was rejected code.

## Where we stand

One tenant, one stage, one read-only tool, no booking, no event log, text only.
A human can ask the receptionist for Thursday's availability from the terminal
and get real hours from a fake agenda; the suite proves when the agenda is and
is not consulted.

## Next

ms-3: stages (`Identify → ChooseSlot → Farewell`), `ConfirmTask` minting a
confirmation token, `book_slot` as an irreversible tool the guard refuses
without it, and a saga with compensation when step 2 fails.
