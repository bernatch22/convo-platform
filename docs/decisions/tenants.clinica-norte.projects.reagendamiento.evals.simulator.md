# `tenants.clinica-norte.projects.reagendamiento.evals.simulator`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/evals/simulator.py`; the code keeps one line per symbol.

## module

The machinery is `core.testing.simulator` — one live session per conversation, a
deterministic stopping controller, one call at a time. What lives here is the
clinic's half of it, and only that: the personas, the goldens, the tool names
that settle a call, and the context each call starts from.

Four batches, because the clinic has four errands and a `SimulatedCaller` opens
every conversation at ONE stage. Five callers move a cita they already have,
three ask for a first one, two change the number the clinic rings them on and
two drop the cita altogether; the lists are concatenated in that order and
`simulate_calls()` returns them in the order `goldens()` names them, which is how
a score is paired back to the call that earned it.

There is deliberately no simulated call for `confirm_attendance`. It is a
compensable `write`, so the consent graph ends at its first computed node and
would report 1.0 without reading a thing — and a green that measured nothing is
worse than no green at all (`evals/dag.py` makes the same argument about
per-errand metrics). That verb is proved where it can be: the goldens, the unit
ring, and the live call at the bottom of `tests/test_stages.py`.

Three of these choices are worth the sentence:

- **The rescheduling calls start at `ChooseSlot`, already identified.** Every
  user turn is a Haiku call for the persona and another for the agent, and
  identification is already pinned by `tests/test_stages.py` with two
  deterministic turns. Paying five conversations' worth of model time to
  re-prove it would buy nothing this metric can read: `book_slot` only exists in
  the stage these calls start in. The new-booking calls start at `NewBooking`
  for the same reason.
- **`book_slot`, `create_appointment`, `update_contact`, `cancel_appointment`
  and `decline` end the call.** The first four mean something irreversible was
  written, the last that the patient said no. None of them needs a judge.
- **The three who back out are the cheapest goldens here.** The consent graph's
  first node is computed, so a conversation where nothing was written ends
  there: they are scored on every model and in every nightly for nothing
  (`tests/test_consent_dag.py` counts the judge calls and gets zero, on the new
  door as on the old ones).

## simulate_calls

Four `SimulatedCaller` batches because a caller opens every conversation at
one stage, and the four errands begin at four. The order is the
concatenation of the four golden lists, which is the contract the suite
pairs scores by.

## identified_context

`prev_agent` matters as much as `customer`. What ChooseSlot knows about the
caller arrives as the previous stage's `summary()` in its `on_enter`, and a
stage entered without one opens by asking for the name again — the right
behaviour, and the wrong conversation to be simulating here.

## contact_context

The same patient as `identified_context` and a different note across the
handoff. `Identify.errand` is what makes the difference: set to CONTACT its
`summary()` hands the next stage the phone number reduced to its last three
digits, which is the whole safeguard of this errand and therefore the thing
a simulated call has to be scored with in place.

## cancellation_context

The same patient again and a third note across the handoff. What
`Identify.errand = CANCEL` changes is not what the stage knows but what it is
told to DO first — look the cita up and read it back — and a simulated call
entered without it would be scoring a stage that opened by asking for a name
nobody needs to give twice.

## unknown_context

The difference from `identified_context` is one absent key. `customer` here
carries a name and a phone and no `appointment_id`, which is what `Identify`
writes when a caller asks for a first cita — and what makes the previous
stage's `summary()` say there is nothing on the book, the sentence NewBooking
opens on.
