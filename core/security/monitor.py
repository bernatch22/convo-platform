"""The agent's side of a supervisor's presence: write it down, and change nothing else.

A supervisor entering a live call must be two things at once. It must be
**invisible** — the caller is never told, and the agent must not greet, must
not re-plan, must not so much as notice — and it must be **on the record**,
because a second human hearing a stranger's call is exactly the fact an audit
comes looking for. Those two pull in opposite directions, and this module is
where they are reconciled: one `supervisor.join` in the caller's own log, and
no other consequence anywhere.

Two roads lead here, and both end at the same `entered`:

1. `participant_connected`, for a supervisor the SFU *does* announce (a
   `takeover`, which is not hidden). The handler exists to say out loud that a
   `sup:` arrival is not a caller — any greet-on-join a project adds later
   must go through `is_supervisor` first, and the LiveKit example that greets
   every joiner is precisely the bug this prevents.
2. a packet on the `supervisor` topic sent by the control plane with its own
   API key, for the hidden case — where the SFU announces nothing at all.

Measured on this box (livekit-server v1.9.1, `tmp/probe_hidden.py`): a
participant that joins with `hidden=True` fires **no** `participant_connected`
on the other clients and never appears in their `remote_participants`; the
server-side `list_participants` sees it perfectly. So road 1 alone would log
nothing for a listening supervisor — the invisibility is real, and road 2 is
what keeps it auditable anyway.

The trust boundary is the same one `core.security.supervisor` states: a packet
whose `participant` is None came from a server SDK holding the API key, and
nothing a participant sends can look like that (measured too,
`tmp/probe_channel.py`). A `{"verb": "join"}` from a browser arrives with an
identity attached and is dropped.

Open source note: "log the second human, tell the agent nothing" is the whole
of live-monitoring compliance for any LiveKit deployment. The reusable half is
this file plus `core.security.supervisor`; the tenant half is only which log
the event lands in.
"""

import json
import logging
from typing import Any

from core.security.supervisor import JOIN, is_supervisor
from core.state.log import record

log = logging.getLogger("platform.supervisor")

# The topic the control plane announces a supervisor's verbs on, agent-only.
TOPIC = "supervisor"

# What this card understands. `steer`, `takeover` and `release` arrive with tk-66a577.
JOIN_VERB = "join"


class SupervisorWatch:
    """One live call's supervisors: each arrival logged once, on the CALLER's log.

    Held by the job for as long as the job lives, which is exactly as long as
    the call. `seen` is what makes the two roads idempotent: a `takeover`
    supervisor is both announced by the SFU and announced by the control
    plane, and one human entering one call is one line in the log.
    """

    def __init__(self, tc: Any) -> None:
        self.tc = tc
        self.seen: set[str] = set()

    def entered(self, identity: str, capability: str = "listen", hidden: bool = True) -> bool:
        """Record that a supervisor is on this call; False when it is not one, or already logged.

        The return value is for tests and for the caller's own logging — the
        agent itself never reads it, because there is nothing for the agent to
        do about a supervisor being there.
        """
        if not is_supervisor(identity) or identity in self.seen:
            return False
        self.seen.add(identity)
        record(self.tc, JOIN, {"identity": identity, "capability": capability, "hidden": hidden})
        log.info(
            "supervisor %s is listening (capability=%s, hidden=%s)", identity, capability, hidden
        )
        return True

    def on_participant(self, participant: Any) -> bool:
        """A participant arrived: log it if it is a supervisor, and ignore it either way.

        Ignoring is the behaviour. Nothing in this method reaches the session,
        the agent or the LLM — a supervisor walking in changes no turn, no
        stage and no prompt.
        """
        identity = str(getattr(participant, "identity", "") or "")
        if not is_supervisor(identity):
            return False
        attributes = dict(getattr(participant, "attributes", None) or {})
        return self.entered(identity, attributes.get("cap", "listen"), hidden=False)

    def on_packet(self, packet: Any) -> bool:
        """A packet on the supervisor topic: obeyed only when the control plane sent it.

        `packet.participant is None` is the whole of the check. The SFU fills
        that field in for every participant-sent packet and leaves it empty
        only for one sent with the deployment's API key, so a browser cannot
        forge a supervisor's arrival by publishing on this topic.
        """
        if getattr(packet, "topic", None) != TOPIC or getattr(packet, "participant", None):
            return False
        verb = _verb(getattr(packet, "data", b""))
        if verb.get("verb") != JOIN_VERB:
            log.debug("supervisor verb not handled by this build: %s", verb.get("verb"))
            return False
        return self.entered(
            str(verb.get("identity", "")),
            str(verb.get("capability", "listen")),
            hidden=bool(verb.get("hidden", True)),
        )


def watch_supervisors(room: Any, tc: Any) -> SupervisorWatch:
    """Wire one room so a supervisor's arrival becomes a log line and nothing else.

    Call it once per job, with the room the job runs in. A room that cannot be
    subscribed to (the console, a test harness, a headless session) still gets
    a watch back, so a caller never has to write an `if` about it.
    """
    watch = SupervisorWatch(tc)
    subscribe = getattr(room, "on", None)
    if subscribe is None:
        return watch
    subscribe("participant_connected", watch.on_participant)
    subscribe("data_received", watch.on_packet)
    return watch


def _verb(data: bytes) -> dict[str, Any]:
    """The announced verb as a dict; anything unreadable is an empty one, never an exception."""
    try:
        parsed = json.loads(bytes(data).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        log.warning("unreadable packet on the %r topic", TOPIC)
        return {}
    return parsed if isinstance(parsed, dict) else {}
