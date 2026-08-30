# ms-3 — stages + confirmation: the conversation becomes a process

**Landed 2026-08-30 · 4 cards (2 by the orchestrator, 2 by Opus workers) · lands on master with this milestone**

## What we set out to do

Turn one prompt with one tool into a process the platform controls: one stage
per phase of the call (Identify → ChooseSlot → Farewell), each with its own
prompt and tools; a confirmation that is a real artefact (`ConfirmTask` mints a
token) and not a sentence the model promised; `book_slot` as an irreversible
tool the platform refuses without that token; and a saga — release the old
hour, take the new one, send the SMS — that undoes itself when the middle step
fails. Then prove the hard policy on conversations nobody scripted, with a
metric that cannot give partial credit, and — after the price golden's GEval
kept flipping — fix the way we judge facts for good.

## What we achieved

- **A rebooking is three writes or none.** "sí, confirmo" → `confirm` mints a
  one-shot token bound to `book_slot(slot=…)` → the saga runs
  `cancel_slot → book_slot → send_sms` → the SMS reads "Clínica Norte: Ana
  García Ruiz, su cita queda el jueves 3 de septiembre a las 09:00 con Dr. Hugo
  Ferrer". The slot at 13:00 is refused by the fake system on purpose:
  `book_slot` fails, `rebook_slot` puts the old appointment back, and the
  receptionist says so ("Su cita del jueves sigue en pie, no se preocupe") and
  offers the other hour. Nothing spoken is a promise the platform has not kept.
- **Consent is a token, not a mood.** `ConfirmationToken(audience=tool:sha(args),
  ttl=120 s, used)`: it authorises exactly one call with exactly those
  arguments, once. The guard refuses four ways — no token, another call's
  token, expired, already spent — each with its own reason (7 tests). The
  executor spends it only after a successful call, so a refused booking can be
  retried inside the window without asking again.
- **Stages hand over a summary, not a transcript.** LiveKit copies no history
  across a handoff. `TenantAgent.on_enter` writes the previous stage's
  `summary()` into its own context before speaking, as a system item placed
  after the instructions, so the 4,360-token `<clinic_knowledge>` prefix every
  stage shares stays byte-identical and cached (`prompt_cached_tokens > 0` on
  ChooseSlot's second turn, tested).
- **Two hard policies as decision graphs.** "Never book before an explicit
  yes": 1.0 on all five simulated calls (two smooth, two that change their
  mind twice, one that backs out). "Every stated fact has a source": 1.0 on all
  ten goldens with **zero judge calls**. Ring-1 suite: 20/21 (see the slip
  below), ToolCorrectness 10/10, ArgumentCorrectness 3/3; 103 unit tests.
  Documented end to end in [`docs/evals.md`](../../docs/evals.md).
- **The whole milestone cost ≈ $0.10 of Anthropic.** Haiku on both sides of
  the line and as the judge; the DAGs decide in code wherever code can.

## What we learned the hard way

1. **A seam that nothing runs is not tested.** `ConfirmTask` passed its own
   `@function_tool` methods as `tools=`; an Agent already collects them, so
   LiveKit refused "duplicate function name: confirm" the instant the task
   took the session over. Seven unit tests on the token and the guard were
   green because none of them started a `ConfirmTask` inside a session. The
   stages card found it on its first end-to-end run. Root cause: the seams
   card tested the parts and not the moment they meet.
2. **A handoff with a spoken line says everything twice.** `hand_off(next,
   said=…)` returned `(Agent, str)`; LiveKit makes the *leaving* stage answer
   with that string, and the arriving stage then speaks in `on_enter`. On a
   phone call that is the same sentence twice. `said` is now optional and
   defaults to silent; what the next stage needs travels in `summary()`.
3. **"13:00" is not a sentence.** The confirmation is read out verbatim, and
   a TTS says "las trece cero cero" (Haiku once read it aloud as "las dos").
   `dates.spoken_moment` renders "a la una de la tarde" for that one line; the
   offer lines keep HH:MM because that is the argument `book_appointment` takes.
4. **The model's tool is not the irreversible act.** The obvious consent metric
   — "was the booking tool called before a yes?" — fails every correct
   conversation, because the prompt tells the model to call `book_appointment`
   the moment the patient picks an hour: reading it back and waiting *is* that
   tool. The write that needs consent is `book_slot`, run by the platform
   after the token exists, and no `RunResult` event says when. The fix was
   structural: `RecordingExecutor` in the harness records the platform's own
   calls per turn and the bridge puts them on the assistant turn.
5. **A judge with no evidence guesses, and guesses differently each run.**
   The price golden scored 0.0 and 0.9 on the same correct answer. GEval splits
   a criterion into steps and each step keeps only its own clause; "an hour
   needs a tool" survived its own exception ("prices come from the sheet"), and
   the judge could not see the sheet anyway. The fix is not a smarter judge:
   **code extracts the facts and matches them against the evidence; the judge
   only ever answers one binary question with the evidence attached.** Two
   "0.0"s in the first run of that graph were correct verdicts on evidence we
   had failed to hand over (`PlatformCall` recorded the word `executed` instead
   of the row; `\b` does not match between `T` and `1` in `2026-09-03T10:00`).
6. **A judge node with the transcript scores the call; with one sentence it
   answers the question.** The consent node gets `evaluation_params=None`
   and reads only the quoted line.
7. **A metric judged one turn earlier than the evidence fails the agent.**
   ArgumentCorrectness failed `specialty="traumatología"` twice: the model had
   learnt it from `find_patient` a turn earlier and the judge could not see
   that turn. `before` turns now enter the case context, and the tool contract
   says keeping the specialty of the appointment being moved is correct.
8. **The judge is a tool-caller with a token cap.** `judge_llm` at
   `max_tokens=200` truncated the `check_intent(success, reason)` call for any
   Spanish reason longer than two sentences and failed as "no arguments".
   Raised to 400, reason written down.
9. **Register is project data.** `ConfirmTask` runs with its own tiny prompt;
   core's neutral wording tuteó a patient the call had treated as "usted", with
   a preamble and markdown bold. The project passes its own
   `CONFIRM_INSTRUCTIONS`.
10. **The agent still slips.** "¿Cuál **te** viene mejor?" once in 21 cases,
    with the instruction "de usted" already in the prompt. The GEval judge was
    right to fail it. Hardening the prompt and a deterministic register node
    are one ms-7 card (`tk-ff61b4`).

## Decisions

- **Compensations are `write`, never `irreversible`.** The platform is undoing
  on the caller's behalf; asking for a second yes to put things back is not a
  conversation anyone wants.
- **The token is spent on success, not on attempt.** A refused or failed
  irreversible call leaves the yes valid for its 120 s; a stage may retry
  without asking again, and says so in a comment.
- **Hard policies are DAGs; GEval keeps tone and form only.** Written into the
  GEval criterion itself: facts are not its business.
- **Deterministic nodes are ours.** DeepEval has none; `DeterministicNode` in
  `dag.py` is the workaround and the upstream PR.
- **One test function for the five simulated calls.** Parametrised, `-n 3`
  would rebuild the fixture per worker and simulate fifteen conversations to
  score five.
- **Haiku everywhere, budget in the brief.** Every worker card now carries the
  cost rule: Haiku for agent, persona and judge; run the suite at most twice.

## Where we stand

Master carries a receptionist that identifies the patient, reads the real
agenda, reads the chosen hour back, books only on a spoken yes, undoes a failed
rebooking, and closes the call — in text. Both hard policies are measured on
every push. Voice providers (Soniox, ElevenLabs, VAD, turn detector) are wired
and unit-tested on the ms-6 branch and wait for ms-4 and ms-5 to land first.

Try it (needs `ANTHROPIC_API_KEY` in `.env`):

```bash
uv run python worker.py console --text
#   > hola, quería cambiar mi cita        → asks for name and phone
#   > Ana García Ruiz, 600123456          → finds Thursday 3 at 10:00, hands off to ChooseSlot
#   > ¿qué huecos hay el martes?          → two hours read back
#   > la primera                          → "…¿lo confirmo?"  (nothing booked yet)
#   > sí                                  → booked + SMS   (say "no" instead: nothing moves)
#   the 13:00 slot always fails: cancel is undone and the agent says so
uv run pytest -m unit -q                    # 103 passed
uv run deepeval test run tests/evals -n 3   # ≈ $0.05, ~2 min
```

Read it:

```bash
nvim -p core/confirm.py core/tools/guard.py core/tools/saga.py core/agents/confirm_task.py core/agents/base.py
nvim -p tenants/clinica-norte/projects/reagendamiento/stages/choose_slot.py tenants/clinica-norte/projects/reagendamiento/stages/identify.py tenants/clinica-norte/adapters/agenda.py tenants/clinica-norte/adapters/sms.py
nvim -p tenants/clinica-norte/projects/reagendamiento/evals/dag.py tenants/clinica-norte/projects/reagendamiento/evals/grounding.py tenants/clinica-norte/projects/reagendamiento/evals/simulator.py tenants/clinica-norte/projects/reagendamiento/evals/metrics.py docs/evals.md
```

Scores per golden and per simulated call, and the four console transcripts:
`tmp/reports/ms-3.html` (generated, not versioned); DeepEval's own HTML in
`tmp/reports/deepeval/`.

## What comes next

**ms-4** — the event log: every stage, tool, confirmation, saga step and turn
(with ttft/e2e) written with a per-session `seq` during the call, SIGKILL-safe
(seams already landed on the ms-4 branch: `python -m convo sessions show`),
plus the observers and the first ring-3 step — a stored session replayed
through the two DAGs above. Then ms-5 (two tenants, one worker) and ms-6
(talk to the agent from the laptop microphone).
