# `tenants.tienda-sur.adapters.tickets`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/adapters/tickets.py`; the code keeps one line per symbol.

## module

Every other fake system here answers about something that already existed when
the phone rang: an order was placed on the web, an appointment was in the book.
A ticket is not. It comes into being mid-call, out of a sentence the customer
said, and it has to be readable by its number on the NEXT call — which is a
different room, a different job and a different process.

That is why this adapter reads the ledger and `FakeOrders` does not. The rule
in `core/adapters/ledger.py` is write-through: a demo adapter records what it
changed so the console can see it, and never reads it back into a conversation,
so no call can be contaminated by what another one wrote. The rule holds
because an order's identity lives in the seeded book — the ledger only ever
carries a NEW STANDING for a row that already existed. A ticket's identity has
nowhere else to live: refuse to read the ledger and `TS-T0003` exists for
exactly as long as the call that opened it, which is not a helpdesk, it is a
sticky note. So this adapter's book is the seed with the ledger merged over it,
in both directions, and the isolation the rule was protecting is kept where it
actually belongs: `tests/conftest.py` gives every test its own ledger file.

It stores the CONSOLE's row shape (`core.adapters.base.LIST_RECORDS`) and reads
tickets back out of it, rather than inventing a second private schema in the
same file. One shape on disk, one reader, and what the operator sees is by
construction what the next call will find.

Open source note: replace each method with an HTTP call to your own helpdesk
(Zendesk, Freshdesk, a table of your own), keep `capabilities()` and the result
shapes, and every layer above — tool, guard, prompt, console — works unchanged.

## FakeTickets._list_records

The console's read, never a tool. The same shop answers this question
twice in one project and with two different shapes — orders here,
tickets there — which is the whole reason nothing in `core` holds a list
of columns or of state words.

## summarise_ticket

The number is the point — it is the join key the console reads and the thing
the customer will quote back next week — and the subject is deliberately not
here. A ticket's subject is whatever a person dictated into it: their
address, their neighbour's name, the order somebody else took delivery of.
The mask would blank the values it knows about; this renderer never hands it
the field at all.

## _as_ticket

The ledger holds one shape and this is what makes that affordable: the
helpdesk reads its own rows out of the console's columns instead of a second
private schema kept in step by hand. `order_id` is the one field the console
never had a column for, so it is recovered from nothing and stays empty; it
is a cross-reference for the operator, not something the caller is told.
