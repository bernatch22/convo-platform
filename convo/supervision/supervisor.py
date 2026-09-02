"""Who counts as a supervisor, and what a supervisor's moves are called in the log.

The trust anchor is the identity the SFU read off a JWT this deployment
signed — never a `{"role": "supervisor"}` field inside a data packet or an RPC
payload. Any participant in a room can write that field; none of them can put
`sup:` in the `sub` of a token they cannot sign. So the agent asks exactly one
question of an incoming verb — `is_supervisor(caller_identity)` — and treats
everything else it is handed as data.

The audit vocabulary lives next to the gate that admits it: the five dotted
kinds a supervisor's presence adds to a session's log (documented with the
rest of the vocabulary in `core.state.log`).

Open source note: a prefix-scoped identity plus role-scoped grants is a
reusable pattern for any LiveKit deployment that lets a second human into a
room already in progress. A stranger changes `SUPERVISOR_PREFIX` and keeps
everything else.
"""

# The one string that separates a supervisor from a caller, an observer and the agent.
SUPERVISOR_PREFIX = "sup:"

# The audit vocabulary: one kind per verb, appended to the caller's own session log.
JOIN = "supervisor.join"  # a supervisor is on the line, hidden, listening
STEER = "supervisor.steer"  # text whispered to the agent, which the caller never hears
TAKEOVER = "supervisor.takeover"  # the human took the line; the agent stopped speaking
RELEASE = "supervisor.release"  # the line handed back to the agent
TRANSFER = "supervisor.transfer"  # the call moved on to somebody else

KINDS: tuple[str, ...] = (JOIN, STEER, TAKEOVER, RELEASE, TRANSFER)


def is_supervisor(identity: str) -> bool:
    """True when this participant identity was minted as a supervisor's — the only gate.

    `""` (a participant the framework could not name) and any other prefix —
    a caller's `tenant:user`, an observer's `observer:<hex>`, the agent's own
    identity — are False, so a missing identity fails closed.
    """
    return identity.startswith(SUPERVISOR_PREFIX)
