# `tenants.clinica-norte.projects.reagendamiento.evals.dag`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/evals/dag.py`; the code keeps one line per symbol.

## module

The shapes live in `core.testing.dag` — was the irreversible tool run and was
the line before it a yes; does every stated fact have a source; does the agent
stay in the register the business speaks. What a clinic owns is what those
questions are asked ABOUT: `book_slot` is the write that moves an appointment,
`create_appointment` is the write that opens a new one, `book_appointment` and
`request_appointment` are the tools the model calls to ask for the yes, a
Spanish "sí, confirmo" is consent, and a patient addressed as "usted" is never
told "te".

Five consent graphs, one question. Four of them watch one write each, for a
suite that already knows which errand it simulated, and `any_write_consent_graph`
watches all four, for a stored session that does not say. The judge's question
is the same wording in all four on purpose: "was this an explicit agreement to
what had just been read out" does not depend on whether a cita existed before or
whether it was a cita at all, and two wordings would make the numbers
incomparable for no gain. What differs between them is only the tool names — so
"did it write?" stays a name in a list rather than an inspection of arguments.

Ms-20 is what proves that shape was worth building. The clinic's third
irreversible verb changes a phone number and touches no appointment, and adding
it to the policy cost one pair of names in a tuple: no node changed, no criterion
was rewritten, and the graph that scores a stored session went from watching two
doors to watching three. A metric that had hard-coded "booking" anywhere would
have needed a fourth graph and a fourth judgement instead.

Ms-20's second half is the same claim tested a fourth time, and this one is a
verb the clinic ALREADY had half of: `cancel_slot` has been in the catalog since
ms-3 as one step of a rescheduling saga. The standalone cancel is a different
promise about undoing it — the hour goes straight back on offer — so it is a
different capability with a different spec, and the policy grew by one more pair
of names. `cancel_slot` is deliberately NOT in this tuple: a saga step the
platform runs itself, inside a booking the caller already agreed to, is not a
door anybody knocks at.

Written this way the whole of the clinic's policy is five pairs of constants and
five one-line factories, and the shop next door reuses the same graphs with its
own.

## any_write_consent_graph

This is the graph a STORED session is scored by, and it has to watch all
three because nobody tells `convo sessions eval` which errand the call was.
Separate metrics would each report 1.0 on a call the others were about — the
graph ends at its first node when its write did not run — and three greens,
two of them measuring nothing, is worse than no metric at all.

It is also the line a new verb joins: ms-20's `update_contact` and
`cancel_appointment` became part of the clinic's consent policy by being
added to `IRREVERSIBLE_TOOLS`, and nothing else in this file or in
`core.testing.dag` moved.
