# `tenants.tienda-sur.projects.pedidos.evals.simulator`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/evals/simulator.py`; the code keeps one line per symbol.

## module

The machinery is `core.testing.simulator`, shared with the clinic next door. What
lives here is the shop's half of it, and only that: three personas, three
goldens, the two tool names that settle a cancellation, and the seeded order each
call starts from.

Two of those choices are worth the sentence:

- **The calls start at `OrderDesk`, already identified.** Every user turn is a
  Haiku call for the persona and another for the agent, and identification is
  already pinned by `tests/test_tienda_stages.py` with two deterministic turns.
  `cancel_order` only exists in the stage these calls start in.
- **`cancel_order` and `decline` end the call.** The first means the order was
  stopped, the second that the customer said no to it. Neither needs a judge.

## identified_context

`prev_agent` matters as much as `customer`. What OrderDesk knows about the
order arrives as the previous stage's `summary()` in its `on_enter`, and a
stage entered without one opens by asking for the order number again — the
right behaviour, and the wrong conversation to be simulating here.
