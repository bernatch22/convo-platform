"""A supervisor on the line: one line in the caller's log, and no other consequence anywhere.

Two roads reach `SupervisorWatch.entered` and both are exercised here: the
`participant_connected` a visible supervisor fires, and the control plane's
packet on the `supervisor` topic — which is the only road for a `listen`
supervisor, because a hidden participant fires nothing at all (measured on
this box, see the module docstring of `core.security.monitor`).

What is NOT asserted anywhere in this file is any effect on the session: there
is none, and that is the point of criterion 2. The watch is handed a context
with a log and nothing else, so a test that started greeting people would have
nothing to greet them with.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from core.security.monitor import TOPIC, SupervisorWatch, watch_supervisors
from core.state.log import EventLog
from core.state.store import MemoryStore

pytestmark = pytest.mark.unit

SESSION = "AJ_call"


@dataclass
class Ctx:
    """The two attributes `core.state.log.record` reads off a context, and nothing else."""

    log: EventLog
    pii_values: tuple[str, ...] = ()


@dataclass
class Participant:
    """A participant as the room hands it over: an identity and the token's attributes."""

    identity: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Packet:
    """A data packet; `participant=None` is the SFU's own word for "a server SDK sent this"."""

    data: bytes
    topic: str | None = TOPIC
    participant: Any = None


@dataclass
class Room:
    """A room that only remembers what was subscribed to it."""

    handlers: dict[str, Any] = field(default_factory=dict)

    def on(self, event: str, handler: Any) -> None:
        self.handlers[event] = handler


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def tc(store: MemoryStore) -> Ctx:
    """A session whose log is already two events old, so `seq` has somewhere to continue from."""
    log = EventLog(SESSION, store)
    log.append("session.start", {"tenant": "clinica-norte"})
    log.append("turn.user", {"text": "buenos días"})
    return Ctx(log=log)


def test_a_hidden_supervisor_is_logged_from_the_control_planes_packet(tc, store) -> None:
    watch = SupervisorWatch(tc)

    assert watch.on_packet(_announced("sup:berna", "listen", hidden=True)) is True

    (event,) = [e for e in store.events(SESSION) if e.kind == "supervisor.join"]
    assert event.payload == {"identity": "sup:berna", "capability": "listen", "hidden": True}


def test_the_join_continues_the_callers_own_sequence(tc, store) -> None:
    SupervisorWatch(tc).on_packet(_announced("sup:berna"))

    assert [(e.seq, e.kind) for e in store.events(SESSION)] == [
        (1, "session.start"),
        (2, "turn.user"),
        (3, "supervisor.join"),
    ]


def test_a_visible_supervisor_is_logged_from_the_rooms_own_arrival(tc, store) -> None:
    watch = SupervisorWatch(tc)

    logged = watch.on_participant(Participant("sup:berna", {"cap": "takeover", "role": "sup"}))

    assert logged is True
    (event,) = [e for e in store.events(SESSION) if e.kind == "supervisor.join"]
    assert event.payload == {"identity": "sup:berna", "capability": "takeover", "hidden": False}


def test_a_caller_arriving_is_not_a_supervisor_and_writes_nothing(tc, store) -> None:
    watch = SupervisorWatch(tc)

    assert watch.on_participant(Participant("clinica-norte:u1")) is False
    assert watch.on_participant(Participant("observer:ab12")) is False
    assert watch.on_participant(Participant("")) is False

    assert [e.kind for e in store.events(SESSION)] == ["session.start", "turn.user"]


def test_one_human_entering_one_call_is_one_line(tc, store) -> None:
    """A takeover is announced twice — by the SFU and by the control plane. Once in the log."""
    watch = SupervisorWatch(tc)

    watch.on_participant(Participant("sup:berna", {"cap": "takeover"}))
    second = watch.on_packet(_announced("sup:berna", "takeover", hidden=False))

    assert second is False
    assert len([e for e in store.events(SESSION) if e.kind == "supervisor.join"]) == 1


def test_a_participant_cannot_forge_a_supervisors_arrival(tc, store) -> None:
    """The packet is trusted for one reason: nobody in the room could have sent it."""
    watch = SupervisorWatch(tc)
    forged = _announced("sup:intruder")
    forged.participant = Participant("clinica-norte:u1")

    assert watch.on_packet(forged) is False
    assert [e.kind for e in store.events(SESSION)] == ["session.start", "turn.user"]


def test_a_packet_on_another_topic_is_none_of_this_modules_business(tc, store) -> None:
    watch = SupervisorWatch(tc)
    elsewhere = _announced("sup:berna")
    elsewhere.topic = "lk.chat"

    assert watch.on_packet(elsewhere) is False
    assert [e.kind for e in store.events(SESSION)] == ["session.start", "turn.user"]


def test_an_unreadable_or_unknown_verb_is_dropped_and_never_raises(tc, store) -> None:
    watch = SupervisorWatch(tc)

    assert watch.on_packet(Packet(data=b"not json at all")) is False
    assert watch.on_packet(Packet(data=json.dumps(["a", "list"]).encode())) is False
    assert watch.on_packet(Packet(data=json.dumps({"verb": "takeover"}).encode())) is False

    assert [e.kind for e in store.events(SESSION)] == ["session.start", "turn.user"]


def test_the_watch_subscribes_to_arrivals_and_to_the_supervisor_topic(tc) -> None:
    room = Room()

    watch = watch_supervisors(room, tc)

    assert room.handlers["participant_connected"] == watch.on_participant
    assert room.handlers["data_received"] == watch.on_packet


def test_a_room_that_cannot_be_subscribed_to_still_returns_a_watch(tc) -> None:
    """The console and the harness have no room; nobody should write an `if` about it."""
    assert isinstance(watch_supervisors(None, tc), SupervisorWatch)


def _announced(identity: str, capability: str = "listen", hidden: bool = True) -> Packet:
    """The packet `core.security.desk` sends into the room, byte for byte."""
    body = {"verb": "join", "identity": identity, "capability": capability, "hidden": hidden}
    return Packet(data=json.dumps(body).encode("utf-8"))
