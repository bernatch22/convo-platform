# `tenants.tienda-sur.adapters.orders`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/adapters/orders.py`; the code keeps one line per symbol.

## module

It stands where the shop's real back office will stand and answers the same
shape: a capability name, a dict of arguments, a plain result. Reading is
`find_order`; writing is `cancel_order` and `restore_order`, the inverse the
saga runs when the customer cannot be told the cancellation went through.

One refusal is deliberate and deterministic, and it is the rule of the whole
project: an order that has already left the warehouse cannot be cancelled. The
adapter raises for it even though the stage checks first — the customer's own
system is the last word on what may happen to an order, and a platform that
only enforced the rule in a prompt would not be enforcing it at all.

Open source note: this file is the template a customer copies. Replace each
method with an HTTP call to your own order API, keep `capabilities()` and the
result shapes, and every layer above (tool, guard, saga, executor, prompt)
works unchanged. An argument the system cannot read raises `ValueError`, which
the executor turns into a sentence the caller hears — never a stack trace.

## FakeOrders._list_records

The console's read, never a tool. The shop answers the same question the
clinic does and with a different shape — `orders`, with an order's own
columns — which is the whole reason nothing in `core` holds a list of
columns: a project with no agenda is not an empty agenda.

The seeded book is what the shop held before anyone rang; the ledger is
every order a call has changed since, across processes, and it wins
wherever both hold the same number.
