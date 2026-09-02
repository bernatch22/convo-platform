"""Fixtures and fakes shared by the handover tests."""

import pytest
from livekit.agents.llm import tool_context

from convo.supervision.control import SupervisorControl
from convo.supervision.supervisor import TRANSFER
from convo.telephony import human
from convo.testing import fake_context
from tests.fixtures.transfer import FakeAPI, FakeRoom, FakeSession, Person

CLINIC = ("clinica-norte", "reagendamiento")
SHOP = ("tienda-sur", "pedidos")
SWITCHBOARD = "+34910000000"
WEB_CALLER = "clinica-norte:web-abc"


@pytest.fixture
def tc():
    return fake_context(*CLINIC)


@pytest.fixture
def livekit(monkeypatch) -> FakeAPI:
    from convo.telephony import handover

    api_client = FakeAPI()
    monkeypatch.setattr(handover, "client", lambda: api_client)
    return api_client


def on_a_phone(tc) -> SupervisorControl:
    """Put the context on a PSTN call: a room whose caller is a SIP leg."""
    tc.channel = "voice"
    tc.supervisor = SupervisorControl(tc, FakeSession(), FakeRoom())
    return tc.supervisor


def in_a_browser(tc) -> SupervisorControl:
    """Put the context on a web call: a real room, a real caller, and no phone leg."""
    tc.channel = "voice"
    room = FakeRoom({WEB_CALLER: Person(WEB_CALLER, kind=1)})
    tc.supervisor = SupervisorControl(tc, FakeSession(), room)
    return tc.supervisor


def tool_names(agent) -> list[str]:
    """Every tool one stage shows the model, by the name the model calls it."""
    return sorted(tool_context.get_function_info(tool).name for tool in agent.tools)


def transfers(tc) -> list:
    """Every `supervisor.transfer` line this session wrote."""
    return [event for event in tc.log.events() if event.kind == TRANSFER]


def _without_the_spec(project):
    """The same project with `transfer_to_human` out of its catalog: the opt-in withdrawn."""
    specs = {name: spec for name, spec in project.tools.specs.items() if name != human.TOOL}
    naked = type(project.tools)(specs)
    return type(project)(**{**project.__dict__, "tools": naked})


def _busy():
    """A carrier answering 486 — the colleague is on another call."""
    from livekit.api import SipCallError

    return SipCallError(
        "internal",
        "Busy Here",
        status=500,
        metadata={"sip_status_code": "486", "sip_status": "Busy Here"},
    )
