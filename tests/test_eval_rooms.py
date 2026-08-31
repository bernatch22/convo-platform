"""The ring-2 door: a room dispatched before anybody joins, and the timeline a caller writes.

Two halves of one seam, both testable without a server. The door is
`POST /evals/rooms`: it must dispatch the agent server-side with the metadata
the router reads, and hand back a ticket that carries NO dispatch of its own —
a second one would seat two agents in the room, both greeting. The harness half
is arithmetic: audio arriving live has gaps nobody sent, and a clip cut by wall
clock has to land on the right samples or every voice metric scores silence.
"""

import json
import os

import jwt as pyjwt
import numpy as np
import pytest
from fastapi.testclient import TestClient
from livekit import api as lkapi

from api import app
from core import rooms
from core.contracts import SessionMeta
from core.router import session_meta
from core.testing.audio import Timeline
from core.testing.fake_job import fake_job_context
from core.testing.ring2 import Transcript

pytestmark = pytest.mark.unit

client = TestClient(app)


class FakeDispatch:
    """Stands in for the SFU: remembers the one request it was handed."""

    def __init__(self) -> None:
        self.request: lkapi.CreateAgentDispatchRequest | None = None
        self.closed = False

    async def create_dispatch(self, request):
        self.request = request
        return request

    async def aclose(self) -> None:
        self.closed = True

    @property
    def agent_dispatch(self):
        return self


@pytest.fixture
def sfu(monkeypatch) -> FakeDispatch:
    """A LiveKit API client that records the dispatch instead of making one."""
    fake = FakeDispatch()
    monkeypatch.setattr(rooms, "_client", lambda: fake)
    return fake


def decoded(token: str) -> dict:
    secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    return pyjwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})


async def test_an_eval_room_is_dispatched_with_the_metadata_the_router_reads(sfu) -> None:
    meta = SessionMeta(tenant="tienda-sur", project="pedidos", channel="voice")

    room = await rooms.create_eval_room(meta, persona="Ana")

    assert room.startswith("eval-tienda-sur-pedidos-"), "a synthetic call says so in its name"
    assert sfu.request.room == room
    assert sfu.request.agent_name == os.getenv("FLEET", "cc")
    assert sfu.request.attributes[rooms.PERSONA_ATTR] == "Ana"
    assert sfu.closed, "one dispatch, then the socket closes"
    routed = session_meta(fake_job_context(metadata=sfu.request.metadata), store=None)
    assert (routed.tenant, routed.project, routed.channel) == ("tienda-sur", "pedidos", "voice")


def test_the_caller_ticket_carries_no_dispatch_of_its_own(sfu) -> None:
    body = {"tenant": "clinica-norte", "project": "reagendamiento", "persona": "Ana"}

    reply = client.post("/evals/rooms", json=body).json()

    claims = decoded(reply["token"])
    assert claims["video"]["room"] == reply["room"], "the grant is an exact room, never a wildcard"
    assert claims["video"]["canPublish"], "a caller with no microphone is not a caller"
    assert "roomConfig" not in claims, "the room already dispatches; two would seat two agents"


def test_an_unknown_project_is_refused_at_the_door(sfu) -> None:
    body = {"tenant": "clinica-norte", "project": "no-such-project"}

    reply = client.post("/evals/rooms", json=body)

    assert reply.status_code == 404
    assert "no-such-project" in reply.json()["detail"]
    assert sfu.request is None, "nothing is created for a project the fleet cannot route"


def test_an_unreachable_sfu_is_a_503_not_a_silent_room(monkeypatch) -> None:
    async def down(*_args, **_kwargs):
        raise rooms.RoomsUnreachable("livekit: connection refused")

    monkeypatch.setattr(rooms, "create_eval_room", down)

    reply = client.post("/evals/rooms", json={"tenant": "tienda-sur", "project": "pedidos"})

    assert reply.status_code == 503, "'the SFU is down' is not 'the agent never answered'"


def test_a_live_timeline_keeps_the_silence_nobody_sent() -> None:
    line = Timeline(rate=16000, origin=100.0)
    tone = np.full(1600, 5000, dtype=np.int16)  # 100 ms of sound

    line.add(tone, at=100.5)
    line.add(tone, at=102.0)

    quiet = line.clip(100.7, 101.9)
    assert quiet.size == int(1.2 * 16000)
    assert not quiet.any(), "the gap between two answers is silence, not the next answer"
    assert np.array_equal(line.clip(102.0, 102.1), tone)


def test_every_clip_says_where_in_the_call_it_belongs() -> None:
    line = Timeline(rate=16000, origin=100.0)
    line.add(np.full(1600, 5000, dtype=np.int16), at=101.0)

    audio = line.audio(101.0, 101.1)

    assert audio is not None
    assert audio.start_time == pytest.approx(1.0), "turn-taking is scored off this offset alone"
    assert audio.duration == pytest.approx(0.1)
    assert line.audio(105.0, 105.5) is None, "a window nothing arrived in carries no audio"


def test_a_transcript_reads_as_a_conversation_with_latencies() -> None:
    script = Transcript(room="eval-x-y-1")
    script.turns.append(_turn("assistant", "Clínica Norte, ¿dígame?", 820.0))
    script.turns.append(_turn("user", "Quiero cambiar mi cita.", None))
    script.turns.append(_turn("assistant", "Claro, ¿su DNI?", 1100.0))

    assert script.said("user") == ["Quiero cambiar mi cita."]
    assert script.latencies_ms == [820.0, 1100.0], "one number per answer, none for the caller"
    assert len(script.case(scenario="reagendar").turns) == 3


def _turn(role: str, content: str, latency_ms: float | None):
    from deepeval.test_case import Turn

    return Turn(role=role, content=content, latency_ms=latency_ms)


def test_the_body_refuses_a_field_nobody_will_read(sfu) -> None:
    body = {"tenant": "tienda-sur", "project": "pedidos", "personna": "Ana"}

    assert client.post("/evals/rooms", json=body).status_code == 422


def test_the_dispatch_metadata_is_json_the_worker_can_parse(sfu) -> None:
    client.post("/evals/rooms", json={"tenant": "tienda-sur", "project": "pedidos"})

    assert json.loads(sfu.request.metadata)["channel"] == "voice", "an eval call is a voice call"
