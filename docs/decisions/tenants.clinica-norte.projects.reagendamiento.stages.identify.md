# `tenants.clinica-norte.projects.reagendamiento.stages.identify`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/stages/identify.py`; the code keeps one line per symbol.

## module

Five exits, and which one a call takes is a tool call in the run rather than a
flag. `identify_patient` finds an existing cita and hands over to ChooseSlot;
`start_new_booking` hands over to NewBooking for a caller who has none;
`start_contact_update` hands over to UpdateContact; and `start_cancellation` and
`start_attendance_confirmation` both hand over to CancelOrConfirm — two tools
into one stage, because the model routes on a docstring and «quiero anularla»
and «llamo para confirmar que voy» are opposite intents that one description
would blur.

The new-booking exit is deliberately NOT what a failed lookup does on its own: a
misheard surname is the commonest error on a phone line, and routing the first
miss straight into a new booking is how a patient ends up with two citas. The
miss asks for the name again; the caller saying they want a new one is what
moves the call. The same rule, harder, on the other three: a caller nobody found
gets a refusal and no handoff — there is no record to change, no cita to cancel
and none to confirm.

## Identify._settle

Written once because the difference between them is genuinely one word.
They are still two TOOLS, and that is not a contradiction: the model
routes on a docstring, and «quiero anularla» and «llamo para confirmar
que voy» are opposite intents that one description would blur. What
happens after the routing is identical, so it lives here.

## Identify._settle_summary

Ms-20's prompt findings, applied: a stage handed a paragraph of context
and no opening decides its own, and both models opened by asking for a
name the previous stage had already taken. So the note ends with the
move — look the cita up, then read it back — and it deliberately does NOT
carry the day, the hour or the professional. That is the same discipline
as `_contact_summary` for a different reason: the next stage is required
to read those off the booking system in this call, and a stage that was
handed them would recite them instead.

## Identify._contact_summary

A phone number is what UpdateContact is about to change and what it must
never read out, and the surest way to stop a stage saying something is to
keep it out of the stage. So the number crosses the handoff as its last
three digits and nothing else: a prompt paragraph can be argued with by a
model, a value it was never given cannot.
