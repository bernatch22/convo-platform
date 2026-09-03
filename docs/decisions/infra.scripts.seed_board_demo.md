# `infra.scripts.seed_board_demo`

The reasoning that used to live in the docstrings of `infra/scripts/seed_board_demo.py`; the code keeps one line per symbol.

## module

Not a fixture generator: nothing here forges a log line. It builds the same
`TenantContext` the router builds, mints the same confirmation token
`ConfirmTask` mints when a caller says yes, and calls `tc.tools.call(...)` —
the real executor, the real guard, the real adapters, the real
`result_summary`, the real PII mask. What lands in the store is byte for byte
what a call writes, which is the only thing `GET /outcomes` reads.

It costs nothing: no LLM, no STT, no keys. It exists because the Board is a
screen about calls that BOOKED something, and a laptop that has only ever been
talked to has none.

    CONVO_DB=tmp/board-demo.db uv run python infra/scripts/seed_board_demo.py
    CONVO_DB=tmp/board-demo.db uv run convo api
    open http://localhost:8090/t/clinica-norte/reagendamiento/board

Point `CONVO_DB` at a throwaway file, never at a store holding real calls.

## transact

`mint` is what `ConfirmTask.confirm` calls, and `confirm.granted` is what it
records. Without both the guard refuses the call, which is the point: this
script cannot write a transaction the platform would not have allowed.
