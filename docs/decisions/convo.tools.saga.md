# `convo.tools.saga`

The reasoning that used to live in the docstrings of `convo/tools/saga.py`; the code keeps one line per symbol.

## module

Rebooking an appointment is three writes on three systems — cancel the old
slot, book the new one, send the SMS — and the second can fail after the first
succeeded. A saga runs the steps in order through the executor (so every step
is catalogued, guarded, timed and logged like any other call) and, when one
fails, runs the `compensation` tool declared on the ToolSpec of each completed
step, last first. The original failure is what the caller hears; a compensation
that fails too is logged, never allowed to hide it.

Compensations run through the same executor, so they need their own ToolSpec
and adapter capability. Declare them `write`, not `irreversible`: the platform
is undoing on the caller's behalf, and asking for a second yes to put things
back the way they were is not a conversation anyone wants.

Open source note: framework-agnostic; the contract is `tc.tools.call` and, for
the audit trail, `tc.log` — which may be absent, and then the saga is silent.

## Saga.step

Without it the compensation receives the step's own arguments, which is
right when undoing needs nothing the call produced (re-book what we
cancelled). Chainable: `Saga(tc).step(...).step(...)`.
