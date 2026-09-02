# `tenants.tienda-sur.projects.pedidos.stages`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/stages/__init__.py`; the code keeps one line per symbol.

## module

Identify finds out which order this is about, OrderDesk says where it is and
cancels it while the warehouse still can, TicketDesk writes down what neither
of those can fix, Farewell closes the call. Each one is a `TenantAgent` with
its own prompt and its own tools, and a stage moves the call on by returning
the next stage from a tool — so the transition is a thing that happened,
recorded in the run, and not a flag somebody set.

TicketDesk has two doors into it and that is deliberate: a customer who already
has their order on the table should not repeat it to open an incident, and a
customer ringing about an incident they opened last week should not be asked
for an order number they may not have. Both doors are exits a stage takes on
purpose, never a fallback a failed lookup falls into — see `ticket_desk.py`.
