# `tenants.clinica-norte.projects.reagendamiento.project`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/project.py`; the code keeps one line per symbol.

## module

ms-3 turns the conversation into a process — Identify, ChooseSlot, Farewell —
and gives it the right to write: `book_slot` is irreversible and unreachable
without a confirmation token, and the three writes that make up a rebooking run
as a saga so a failure halfway leaves the patient's old appointment standing.

ms-20 also closes the two verbs a reception has and this project did not: a cita
could be moved and created, and only ever cancelled as the first half of a move.
`cancel_appointment` is the standalone cancel — the fourth irreversible door,
and the one that gives an hour back instead of taking one, which is why the
freed slot reappears in `find_availability` and why the spec declares no
compensation. `confirm_attendance` is its opposite in every way: the patient
rang to say they ARE coming, nothing is taken from them, and it is a plain
`write` with `rebook_slot` as its undo. Both live in one stage, because the
conversation is one conversation — the cita you already have, and what you want
done with it that is not moving it.

ms-20 adds the third, and it is the first one that is not an appointment:
`update_contact` changes the number the clinic rings the patient on. The verb is
only reachable once the caller has been found on the book — an unidentified
caller cannot change anybody's data — and it goes through the same door as the
other two, which is the point: a new irreversible verb is a ToolSpec, a stage
and a consent graph name, not a new mechanism.

ms-18 adds the second errand and, with it, the second irreversible door.
`Identify` now has two exits and `create_appointment` opens a cita for somebody
the book had never held — through the same guard, the same `ConfirmTask` and a
saga of its own. The project keeps its name: what a caller asks reception for is
an appointment, and whether one already existed is the platform's problem.

The catalog below is the whole of what this project may call. It is data the
platform reads before every call, not documentation: a tool missing from here
cannot run, however convincingly the model asks for it, and the side effect
declared on each spec is what decides whether a caller has to say yes first.

Every spec here also declares a `result_summary` (ms-7): the one line of a
result the session log is allowed to keep, rendered by the adapter that
produced it and masked by the platform before it is written. Reading a
rescheduling call back months later — or scoring it with the grounding metric —
is the difference between "the agent said nine o'clock" and "the agenda offered
nine o'clock and the agent said it".
