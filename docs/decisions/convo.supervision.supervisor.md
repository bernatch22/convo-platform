# `convo.supervision.supervisor`

The reasoning that used to live in the docstrings of `convo/supervision/supervisor.py`; the code keeps one line per symbol.

## module

The trust anchor is the identity the SFU read off a JWT this deployment
signed — never a `{"role": "supervisor"}` field inside a data packet or an RPC
payload. Any participant in a room can write that field; none of them can put
`sup:` in the `sub` of a token they cannot sign. So the agent asks exactly one
question of an incoming verb — `is_supervisor(caller_identity)` — and treats
everything else it is handed as data.

The audit vocabulary lives next to the gate that admits it: the five dotted
kinds a supervisor's presence adds to a session's log (documented with the
rest of the vocabulary in `convo.state.log`).

Open source note: a prefix-scoped identity plus role-scoped grants is a
reusable pattern for any LiveKit deployment that lets a second human into a
room already in progress. A stranger changes `SUPERVISOR_PREFIX` and keeps
everything else.

## is_supervisor

`""` (a participant the framework could not name) and any other prefix —
a caller's `tenant:user`, an observer's `observer:<hex>`, the agent's own
identity — are False, so a missing identity fails closed.
