# `tenants.tienda-sur.tenant`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/tenant.py`; the code keeps one line per symbol.

## module

The second business on the same worker, and the point of it: nothing in `core/`
knows a clinic from a shop. What changes between the two tenants is data —
adapters, prompts, knowledge, tools, voice and register — and what does not
change is every line of the runtime that carries them.

## TiendaSurTenant.build_adapters

Three of them: the order system, the helpdesk and the SMS gateway. The
executor picks whichever one declares the capability a tool asks for, so
adding a system (a payment gateway, a returns portal) is adding a line
here — no stage and no tool changes. The helpdesk is the proof: it
arrived a whole milestone later and this is the only line of wiring it
needed.

Order matters for exactly one reader. The console asks every system that
offers a record view for it (`core.business`), and it draws them in this
order, so the orders the shop lives on lead and the incident queue
follows.
