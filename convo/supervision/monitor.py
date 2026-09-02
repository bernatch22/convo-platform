"""The agent's side of a supervisor's presence: write it down, and change nothing else.

Decisions: docs/decisions/convo.supervision.monitor.md
"""

import asyncio
import json
import logging
from typing import Any

from livekit.rtc import RpcError

from convo.state.log import record
from convo.supervision.control import NotASupervisor, SupervisorControl, UnknownVerb
from convo.supervision.supervisor import JOIN, RELEASE, STEER, TAKEOVER, TRANSFER, is_supervisor
from convo.telephony.transfer import TransferRefused

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
    """One live call's supervisors: each arrival logged once, on the CALLER's log."""

    def __init__(self, tc: Any, control: SupervisorControl | None = None) -> None:
        self.tc = tc
        self.control = control
        self.seen: set[str] = set()

    def entered(self, identity: str, capability: str = "listen", hidden: bool = True) -> bool:
        """Record that a supervisor is on this call; False when it is not one, or already logged."""
        if not is_supervisor(identity) or identity in self.seen:
            return False
        self.seen.add(identity)
        record(self.tc, JOIN, {"identity": identity, "capability": capability, "hidden": hidden})
        log.info(
            "supervisor %s is listening (capability=%s, hidden=%s)", identity, capability, hidden
        )
        return True

    def on_participant(self, participant: Any) -> bool:
        """A participant arrived: log it if it is a supervisor, and ignore it either way."""
        identity = str(getattr(participant, "identity", "") or "")
        if not is_supervisor(identity):
            return False
        attributes = dict(getattr(participant, "attributes", None) or {})
        return self.entered(identity, attributes.get("cap", "listen"), hidden=False)

    def on_packet(self, packet: Any) -> bool:
        """A packet on the supervisor topic: obeyed only when the control plane sent it."""
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
        """Run one verb from a callback that cannot await; False when there is nowhere to run it."""
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
    """Wire one room so a supervisor's arrival is logged and a supervisor's verbs are obeyed."""
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
    """Answer `supervisor.steer|takeover|release` on this job's participant; return what it took."""
    register = getattr(getattr(room, "local_participant", None), "register_rpc_method", None)
    if register is None:
        log.debug("no local participant to register supervisor verbs on")
        return ()
    for kind in RPC_VERBS:
        register(kind, verb_handler(control, kind))
    return RPC_VERBS


def verb_handler(control: SupervisorControl, kind: str):
    """One RPC method's handler: gate on the signed identity, run the verb, answer with JSON."""

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
