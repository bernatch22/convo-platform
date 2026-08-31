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

The other four verbs — `steer`, `takeover`, `release`, `transfer` — are the
same idea pointed the other way: they DO change the conversation, so they reach
`core.security.control.SupervisorControl` and never touch the session from
here. Two roads again, and on purpose:

3. `supervisor.steer` / `.takeover` / `.release` / `.transfer` as **RPC** on the agent's own
   participant. This is the road a supervisor's browser uses, and the reason
   the trust anchor works: the SFU puts `caller_identity` on the invocation
   off the JWT it verified, so `is_supervisor` is asking about a signature and
   not about a field somebody typed. The RPC method names ARE the audit kinds
   in `core.security.supervisor` — one string, one verb, one log line.
4. the same `supervisor` topic as the join, for a control plane that would
   rather whisper server-side (an escalation rule, a compliance trigger) than
   hold a browser open. Same `participant is None` anchor, same handler.

Open source note: "log the second human, tell the agent nothing" is the whole
of live-monitoring compliance for any LiveKit deployment. The reusable half is
this file plus `core.security.supervisor`; the tenant half is only which log
the event lands in.
"""

import asyncio
import json
import logging
from typing import Any

from livekit.rtc import RpcError

from core.security.control import NotASupervisor, SupervisorControl, UnknownVerb
from core.security.supervisor import JOIN, RELEASE, STEER, TAKEOVER, TRANSFER, is_supervisor
from core.state.log import record
from core.telephony.transfer import TransferRefused

log = logging.getLogger("platform.supervisor")

# The topic the control plane announces a supervisor's verbs on, agent-only.
TOPIC = "supervisor"

# What a packet on that topic may say. `join` is a fact; the other four are orders.
JOIN_VERB = "join"
CONTROL_VERBS: dict[str, str] = {
    "steer": STEER,
    "takeover": TAKEOVER,
    "release": RELEASE,
    "transfer": TRANSFER,
}

# The RPC methods this job answers — the audit kind is the method name, exactly.
RPC_VERBS: tuple[str, ...] = (STEER, TAKEOVER, RELEASE, TRANSFER)

# The code an RPC refusal comes back to the browser as; `message` says which refusal.
REFUSED = RpcError.ErrorCode.APPLICATION_ERROR


class SupervisorWatch:
    """One live call's supervisors: each arrival logged once, on the CALLER's log.

    Held by the job for as long as the job lives, which is exactly as long as
    the call. `seen` is what makes the two roads idempotent: a `takeover`
    supervisor is both announced by the SFU and announced by the control
    plane, and one human entering one call is one line in the log.
    """

    def __init__(self, tc: Any, control: SupervisorControl | None = None) -> None:
        self.tc = tc
        self.control = control
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
        body = _verb(getattr(packet, "data", b""))
        verb = str(body.get("verb", ""))
        if verb == JOIN_VERB:
            return self.entered(
                str(body.get("identity", "")),
                str(body.get("capability", "listen")),
                hidden=bool(body.get("hidden", True)),
            )
        if verb in CONTROL_VERBS:
            return self.spawn(CONTROL_VERBS[verb], str(body.get("identity", "")), body)
        log.debug("supervisor verb not handled by this build: %s", verb)
        return False

    def spawn(self, kind: str, identity: str, body: dict[str, Any]) -> bool:
        """Run one verb from a callback that cannot await; False when there is nowhere to run it.

        The room's `data_received` handler is synchronous and the verbs are
        not, so the work becomes a task on the job's own loop. Nothing waits
        for it: the control plane already has its 202, and what the verb did
        lands in the log either way.
        """
        if self.control is None:
            log.warning("%s arrived with no live session to aim it at", kind)
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.warning("%s arrived outside a running loop; dropped", kind)
            return False
        loop.create_task(self._run(kind, identity, body))
        return True

    async def _run(self, kind: str, identity: str, body: dict[str, Any]) -> None:
        """Apply a verb that arrived by packet: a bad one is a log line, never a dead job."""
        try:
            await self.control.apply(kind, identity, body)
        except (NotASupervisor, UnknownVerb, ValueError, TransferRefused) as refused:
            log.warning("%s refused: %s", kind, refused)
        except Exception:  # noqa: BLE001 — a fire-and-forget task must not die silently
            log.exception("%s failed on %s", kind, self.tc.label())


def watch_supervisors(
    room: Any, tc: Any, control: SupervisorControl | None = None
) -> SupervisorWatch:
    """Wire one room so a supervisor's arrival is logged and a supervisor's verbs are obeyed.

    Call it once per job, with the room the job runs in. A room that cannot be
    subscribed to (the console, a test harness, a headless session) still gets
    a watch back, so a caller never has to write an `if` about it — and with no
    `control` the job simply has no verbs, which is what a console run wants.
    """
    watch = SupervisorWatch(tc, control)
    subscribe = getattr(room, "on", None)
    if subscribe is None:
        return watch
    subscribe("participant_connected", watch.on_participant)
    subscribe("data_received", watch.on_packet)
    if control is not None:
        register_verbs(room, control)
    return watch


def register_verbs(room: Any, control: SupervisorControl) -> tuple[str, ...]:
    """Answer `supervisor.steer|takeover|release` on this job's participant; returns what it took.

    The gate is `SupervisorControl.apply`, which asks `is_supervisor` of the
    `caller_identity` the SFU read off the JWT — so a caller, an observer or
    anyone else who guessed the method name is refused before a single word
    reaches the conversation.
    """
    register = getattr(getattr(room, "local_participant", None), "register_rpc_method", None)
    if register is None:
        log.debug("no local participant to register supervisor verbs on")
        return ()
    for kind in RPC_VERBS:
        register(kind, verb_handler(control, kind))
    return RPC_VERBS


def verb_handler(control: SupervisorControl, kind: str):
    """One RPC method's handler: gate on the signed identity, run the verb, answer with JSON.

    Every refusal comes back as an `RpcError` the browser can read, because a
    supervisor whose whisper was rejected has to be told — a silent no-op looks
    exactly like a whisper the agent ignored.
    """

    async def handle(data: Any) -> str:
        identity = str(getattr(data, "caller_identity", "") or "")
        body = _verb(str(getattr(data, "payload", "") or "").encode("utf-8"))
        try:
            return json.dumps(await control.apply(kind, identity, body))
        except NotASupervisor as refused:
            log.warning("%s from %r refused: not a supervisor", kind, identity)
            raise RpcError(REFUSED, "not a supervisor") from refused
        except (UnknownVerb, ValueError, TransferRefused) as bad:
            raise RpcError(REFUSED, str(bad)) from bad

    return handle


def _verb(data: bytes) -> dict[str, Any]:
    """The announced verb as a dict; anything unreadable is an empty one, never an exception."""
    try:
        parsed = json.loads(bytes(data).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        log.warning("unreadable supervisor payload (topic %r, or an RPC body)", TOPIC)
        return {}
    return parsed if isinstance(parsed, dict) else {}
