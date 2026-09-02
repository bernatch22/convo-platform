# `tenants.clinica-norte.adapters.patients`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/adapters/patients.py`; the code keeps one line per symbol.

## module

A rescheduling call starts from an appointment that exists, so the fake agenda
has to know a handful of patients before anyone picks up the phone. Real
systems look this up by phone number and confirm with a name; so does `lookup`,
and it accepts either — a caller who reads their number out and a caller who
only gives a name both get identified, which is what happens on a real line.

Since ms-20 the book is also written to. `update_phone` is the setter behind
the clinic's third irreversible verb: the number the clinic calls a patient on
is data the patient owns, and a caller who has been identified may change it.
It moves every appointment of the same person at once, because a number belongs
to a person and not to a row.

Never real data: the names are invented and the phone numbers are in the
Spanish 600-block reserved for fiction. A customer replaces this module with
their CRM and keeps `lookup`'s two arguments and its return shape.

## lookup

The phone wins when both are given: two patients can share a name and a
misheard surname is the commonest error on a phone line, while a number the
caller reads out digit by digit is the strongest identifier we get.

## update_phone

Every appointment of the same patient moves together. A phone number is a
property of the person, not of one row, and a clinic that changed the number
on the cita the caller happened to mention would still ring the old one for
the next appointment — which is the failure this verb exists to fix.

The refusal is the point of the `ValueError`: an id the book does not hold
is a caller nobody identified, and the platform must not invent a record to
write into.

## last_digits

A Spanish caller validates a number on file the way a bank does it — «acaba
en 456» — and that idiom is a data-protection rule with a voice: the person
who really owns the number recognises three digits, and somebody guessing
learns nothing worth having. It lives here, next to the records, because the
prompt that speaks it and the log line that stores it must not drift into two
different idioms.

## _same_person

Patients give a first name and one surname where the book holds two, so an
exact comparison would fail almost every real call.
