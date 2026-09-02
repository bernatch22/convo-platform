# `tenants.clinica-norte.projects.reagendamiento.helpers`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/helpers.py`; the code keeps one line per symbol.

## masked_phone

Validation without disclosure, which is the whole shape of this errand. The
patient rings because the number the clinic holds is wrong, so the agent has
to make sure they are both talking about the same record — and reading nine
digits out to whoever picked up the phone would hand a stranger the very
datum the call is about to change. Three digits are recognised instantly by
the person who owns them and are worth nothing to anybody else, which is why
every bank in Spain says a number this way.

`patients.last_digits` is the tail, this is the sentence: one place decides
how much, one place decides how it sounds.

## normalise_phone

Spoken numbers arrive with spaces, dots and dashes in them, and a Spanish
mobile is nine digits. Anything shorter is a number that was misheard rather
than a number that was given, and the stage asks again instead of writing it.

## spoken_phone

Nine digits in a row are read out as one enormous cardinal — «seiscientos
ochenta y nueve millones…» — which is not a number anybody can check against
the one they just said. Three groups of three is how the number is printed
on every Spanish document and how it is said out loud.

## contact_confirmation_question

Rendered here from the digits the platform is about to write, never by the
model, for the same reason as the two booking questions: what the caller
agreed to and what is written have to be the same thing by construction. The
NEW number is read out whole — the caller said it seconds ago, and a
confirmation that masked it would be asking somebody to agree to a number
they cannot hear.

## appointment_line

Rendered from the row the booking system just returned, and rendered HERE
rather than in the summary the previous stage leaves, for a reason the evals
ring can see: an hour a model recites off a note is an hour with no source in
the call, and `grounded_facts_dag` is right to escalate it. Coming back as a
tool output, the day, the hour and the professional are evidence — the same
property that lets a replayed call prove the receptionist read the agenda
instead of guessing.

The hour is written as the clock writes it (`spanish_moment`), not as a
person says it, exactly like `_offer`: the shared paragraph in `reception.py`
is what turns 10:00 into "las diez de la mañana" out loud, and a tool that
did it too would be deciding the wording twice.

## cancellation_question

The same rule as the two booking questions and the contact one: rendered by
the platform from the row the write is about to receive, never by the model.
«¿se la anulo?» names what is about to happen to the cita the caller has just
heard read back, and there is no softer verb for it — the hour is on offer to
somebody else a second later.

## confirmation_question

A confirmation the model writes is a confirmation the model can soften, and
"¿le va bien el jueves?" is not consent to move an appointment. The words
are built here from the row the agenda returned, so what the caller agrees
to and what the platform books are the same thing by construction.

## new_confirmation_question

Same rule as `confirmation_question` and a different verb: nothing is being
moved, so «¿lo confirmo?» would be asking about a change that does not
exist. «¿se la reservo?» names what the platform is about to do, and the day,
the hour and the professional come off the agenda's own row.

## _offer

Two, not the three the agenda returns, because how many options a caller can
hold in their head on a phone call is a decision this project makes once —
not arithmetic the model has to do under pressure every turn. Asking it in
the prompt to name two out of a list of three produced exactly the sentence
you would expect: three hours read out, then "¿cuál de las dos primeras?".
The rest of the day is not lost; the last line says so, and the model asks
again if neither works.

The agenda's slot id is deliberately left out. Everything in here is text a
voice agent may read aloud, and `sl-20260903-1100-trau` is not a sentence.
The stage keeps the ids for itself and the model chooses by the hour it
just offered, which is also what the patient says out loud.
