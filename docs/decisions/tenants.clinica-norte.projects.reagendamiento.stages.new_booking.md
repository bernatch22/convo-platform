# `tenants.clinica-norte.projects.reagendamiento.stages.new_booking`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/stages/new_booking.py`; the code keeps one line per symbol.

## module

The same shape as ChooseSlot and deliberately not the same stage. A caller with
no cita has two things still missing — the specialty and the day — nothing to
release before the new hour is taken, and nothing to fall back on when the
booking system says no. The write is its own irreversible tool
(`create_appointment`), so `guard.check` and the consent metric each watch one
name, and the saga is two steps instead of three: take the hour, tell the
patient. If either fails, the compensation cancels what was written and the
caller is told plainly that nothing is on the book.

## _booking

Two steps where a rescheduling has three: there is no earlier hour to
release. The cancel that undoes `create_appointment` is declared on its spec
as the compensation, so a failed SMS still takes the cita off the book rather
than leaving one nobody was told about.

`undo_args` is not optional here, and this is the one place the difference
bites: the saga's default hands a compensation the STEP's own arguments, and
`create_appointment` is called with a slot id while `cancel_slot` needs the
appointment id the write produced. Rebooking gets away with the default
because the cancel it undoes was already keyed by appointment; a creation has
no such id until the row exists.
