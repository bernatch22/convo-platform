# `tenants.tienda-sur.projects.pedidos.evals.test_ring2`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/evals/test_ring2.py`; the code keeps one line per symbol.

## module

The clinic's `test_ring2.py` is this file with two names changed, and that is
the point: one runtime, two businesses, and the eval layer has to look like it
too. What differs is entirely data — the shop tutea, it cancels orders instead
of moving appointments, and its goldens are in its own folder.

    deepeval test run tenants/tienda-sur/projects/pedidos/evals/test_ring2.py

Needs the dev stack up — `docker compose -f infra/compose/dev.yml up`, `uvicorn
api:app --port 8090`, `python worker.py dev` — plus `ANTHROPIC_API_KEY`,
`ELEVENLABS_API_KEY` and `SONIOX_API_KEY`. `CONVO_API` points it at another
control plane; the nightly run uses it to call the box.

Both goldens end in a cancellation, so `consent_policy` here is never the empty
kind that passes because nothing irreversible happened: `cancel_order` is in
the log, and the graph has to find a yes in the line before it.
