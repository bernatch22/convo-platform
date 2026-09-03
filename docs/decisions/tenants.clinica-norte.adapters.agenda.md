# `tenants.clinica-norte.adapters.agenda`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/adapters/agenda.py`; the code keeps one line per symbol.

## module

It stands where the clinic's real booking system will stand and answers the same
shape: a capability name, a dict of arguments, a plain result. Reading is
`find_availability` and `find_patient`; writing is `cancel_slot`, `book_slot`,
`create_appointment`, `update_contact`, `cancel_appointment`,
`confirm_attendance` and `rebook_slot`, the inverse of the cancel that the saga
runs when a booking falls over halfway.

`cancel_appointment` and `cancel_slot` write the same field and are deliberately
two capabilities, for the reason `book_slot` and `create_appointment` are two.
`cancel_slot` is a STEP: the saga releases an hour it is about to replace, and
if the replacement fails `rebook_slot` puts it back milliseconds later, before
anybody could have been offered it. `cancel_appointment` is the whole errand —
the patient is not coming, the hour goes back into the pool
(`find_availability` offers it to the next caller from that moment), and no
compensation can promise it is still there. Same field, two different promises
about undoing it, so two specs and two names in the consent policy.

`confirm_attendance` is the one write here a caller does not have to agree to
twice. The patient rang to say they are coming; marking the row `confirmed`
takes nothing away from them and `rebook_slot` puts it back to `booked` if it
was ever wrong, which is what `write` with a compensation means.

`update_contact` is the odd one out and says something about the taxonomy: it
touches no hour at all. It changes the number the clinic calls the patient on,
which is the patient's data rather than the agenda's, and it is the one write
here with no inverse — nobody keeps the number it replaced, so its spec declares
`irreversible` and lists no compensation.

`book_slot` and `create_appointment` write the same row and are deliberately two
capabilities. One takes an hour for a patient the book already holds — a
rescheduling, released hour and all — and the other opens a record for somebody
who had nothing. A real agenda distinguishes them (the second one creates the
patient), the catalog gives them separate specs, and the consent metric watches
one name each: a single capability would leave "which write ran?" a question
about arguments rather than about a name in a list.

One failure is deliberate and deterministic: a slot at 13:00 (`-1300-` in its
id) is always rejected. It is the demo's "the customer's system said no" case,
and it exists so the compensated path can be reproduced on demand instead of
waited for.

Open source note: this file is the template a customer copies. Replace each
method with an HTTP call to your own agenda, keep `capabilities()` and the
result shapes, and every layer above (tool, guard, saga, executor, prompt)
works unchanged. An argument the system cannot read raises `ValueError`, which
the executor turns into a sentence the caller hears — never a stack trace.

## FakeAgenda.find_availability

A closed day (Sunday) legitimately has none: an empty list is an answer,
not a failure, and the receptionist says so and offers another day.

What the seed generates is the day as it stood before anybody rang. An
hour a caller gave back in this session is merged into it, earliest
first, which is the whole reason a cancellation is worth taking over the
phone: the clinic does not lose the half hour, the next caller is
offered it, and "se la he liberado" stops being a figure of speech.

## FakeAgenda._create_appointment

A new patient needs a name and a number — the row is the only record of
them and the SMS has nowhere else to go — so an empty one is a
`ValueError` rather than a nameless appointment nobody can find again.
The refused hour behaves exactly as it does for a rescheduling: the
clinic's system says no at 13:00 whichever door you knock at, and the
saga above compensates the same way.

## FakeAgenda._cancel_slot

It does NOT give the hour back to `find_availability`, and that is the
difference from `cancel_appointment`. The saga is about to book the
replacement; an hour offered to another caller in between is an hour the
compensation could not return.

## FakeAgenda._cancel_appointment

The write with no way back, which is why its spec is `irreversible` and
nothing reaches this method without a token. `rebook_slot` can still put
the WORD back on the row, but from the moment `_release` runs the hour is
on offer to whoever rings next — so an "undo" would be a promise about
somebody else's booking, and a compensation that cannot be honoured is
worse than none.

## FakeAgenda._confirm_attendance

The one write of this project that needs no second yes. Nothing is taken
from the patient — the cita stays the same day, the same hour and the
same professional — and `rebook_slot` sets the row back to `booked` if it
was ever wrong, which is exactly what a `write` with a compensation
means. Asking somebody to confirm their confirmation is a conversation
nobody wants.

## FakeAgenda._update_contact

The write the clinic cannot undo for you: from the moment it lands, the
number the centre rings is the new one, and the old one is not kept
anywhere for a compensation to put back. That is why its spec declares
`irreversible` and why nothing reaches this method without a token.

An unknown appointment is a `ValueError` and never a new row
(`patients.update_phone`): the identifier is the caller's identity here,
so writing into a record the book does not hold would be updating a
stranger.

## FakeAgenda._release

The slot id is rebuilt from the row rather than remembered, because the
book is what a real agenda would hand back and a cita does not carry the
id of the slot it was once booked into. `slots.slot_id` is the one place
that shape is decided, so the hour reappears with the identifier
`book_slot` would need to take it again.

## FakeAgenda._given_back

Matched on the slot id, which already carries the day and the specialty:
an hour freed in traumatología is a traumatología hour, and offering it
to somebody asking for the centre's general agenda would be offering a
professional who does not do that consultation.

## FakeAgenda._list_records

The console's read, never a tool: no stage may call it and no model ever
sees it. It answers with the clinic's own shape and the clinic's own
words for a state, so `convo/` renders a table it has no vocabulary for.

Two sources, in this order. The seeded book is what the clinic held
before anyone rang; the ledger is every row a call has written since,
across every process, and it wins wherever both hold the same id — a
cita cancelled at eleven is cancelled, whatever the seed still says.

## summarise_availability

Every field of a slot is clinic data — an ISO moment, a professional, an
opaque id — and none of it identifies the person on the phone, so the rows
can be kept whole. That is what lets a replayed call prove an hour the
receptionist read out came off the agenda instead of out of the model.

## summarise_patient

The appointment the caller already has is the fact a replayed call could
never ground — reception reads it back in the first minute of every
rescheduling call — and it is also the one result here that carries a
person. The name is rendered anyway and the executor masks it, so the log
ends up holding `An*************`: enough for an auditor to see that
somebody was found and which of two callers it was, and nothing more. The
phone is simply not rendered; a masked number would say the same thing
twice.

## summarise_contact

The one summary in this project written already masked. The others render
what the adapter returned and let the platform's mask blank it, which works
because the value being protected is a value some ToolSpec declared — and
here that is exactly the field the line is ABOUT. A summary that rendered
the number whole and relied on the mask would read `68*******` and tell an
auditor nothing; the clinic's own idiom (`patients.last_digits`) says which
number the record now holds, in the same three digits the caller heard read
back, and no more.

## summarise_change

`book_slot`, `cancel_slot` and `rebook_slot` all answer with an appointment
id and one more field — the moment it now holds, or the status it now has —
so one renderer covers the three and a saga's undo reads in the log as
plainly as the write it undid. Nothing here names a person: the patient and
the phone were arguments, and the log already carries them masked.
