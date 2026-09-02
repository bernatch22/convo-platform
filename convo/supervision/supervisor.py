"""Who counts as a supervisor, and what a supervisor's moves are called in the log.

Decisions: docs/decisions/convo.supervision.supervisor.md
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
    """True when this participant identity was minted as a supervisor's — the only gate."""
    return identity.startswith(SUPERVISOR_PREFIX)
