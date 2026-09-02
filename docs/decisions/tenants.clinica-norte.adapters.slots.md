# `tenants.clinica-norte.adapters.slots`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/adapters/slots.py`; the code keeps one line per symbol.

## module

Split out of `agenda.py` so the adapter is only the port — capabilities in,
results out — and this file is the arithmetic behind it: pure functions and
data, no state, no I/O, every rule readable in one screen.

The generator is seeded by day and specialty, so the same question always gets
the same answer: a test can assert on an hour and a demo run twice tells the
same story.

Open source note: a customer replaces `free_slots` with a call to their own
agenda and keeps the `{id, when, doctor}` shape. Two rules the port must keep:
`when` is an ISO timestamp, never a phrase in a language (the project turns it
into words), and `id` is opaque to the caller — it is what `book_slot` books.
