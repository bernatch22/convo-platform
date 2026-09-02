# `tenants.tienda-sur.adapters.ticketbook`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/adapters/ticketbook.py`; the code keeps one line per symbol.

## module

An order exists before anyone rings; a ticket does not. That single difference
is why this module has one function the order book never needed — `mint`, which
hands out the next free number — and why the ids it mints look the way they do:
`TS-T0007` is read out loud over the phone, digit by digit, so it is short, it
carries the shop's own prefix, and it can never be mistaken for an order.

Never real data: the names are invented and the phone numbers are in the
Spanish 600-block reserved for fiction. A customer replaces this module with
their own helpdesk API and keeps `lookup`, `mint` and the row shape.

## lookup

The number wins when both are given: it identifies one incident, while a
phone identifies a customer who may have several — and when only a phone
arrives, the most recent one is the one they are calling about.

## mint

Sequential and not random on purpose: the number is dictated over the phone
and typed back in by hand on the next call, so four digits a person can read
without spelling beats an opaque id nobody can repeat. The book it counts
over is the merged one — seed plus ledger — so a second process picks up
where the first left off instead of minting a number that already exists.
