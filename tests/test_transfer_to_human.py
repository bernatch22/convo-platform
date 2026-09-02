"""Handing the call to a person as a verb of the AGENT: the number, the rule, the REFER.

`test_transfer.py` pins what a SUPERVISOR's transfer does. This pins the other
door — the agent deciding «le paso con un compañero» because the caller asked —
and the thing that makes it different is not the SIP: it is that the verb can be
absent.

Five claims, one per section.

1. A tool that cannot work is not offered. The clinic names a `transfer_number`
   and every one of its stages carries `transfer_to_human`; the shop declares
   the same spec, names no number, and no stage of it has ever heard of the
   tool. The prompt never names a verb the model does not have — that is the
   surest way to have it reach for one — but it is not silent either: a shop
   with nobody to pass a call to is told so, because silence is what produced
   «Entiendo, ahora mismo te paso» on a call nobody could ever transfer.
2. The console owns the number. E.164 or empty — and empty is not a refusal, it
   is how a supervisor takes the verb away — with the refusal sentence naming
   the shape a REFER can carry, and the whole thing readable on the pipeline
   screen before anybody discovers it by failing.
3. On a phone call the verb REFERs the caller's own leg to that number, and one
   `supervisor.transfer` line in the caller's log carries the mode and the
   outcome — the ms-15 vocabulary, not a second one.
4. A REFER the carrier refuses is an ANSWER: `ok=False` means the caller is
   still on the line, and what the model reads back says exactly that and tells
   it to keep helping.
5. A chat is told the truth, and so is a browser call on a box that cannot dial
   out. A chat has no audio to join, ever; a browser call without
   `SIP_OUTBOUND_TRUNK_ID` is refused AT THE DOOR — before anybody's phone has
   rung — with the log line naming the variable. Neither asks the SFU for
   anything, both attempts are written down, and the model gets a `ToolError`
   with what it CAN offer.
6. A browser caller with a trunk gets the phone brought to THEM. No SIP leg to
   REFER, so `CreateSIPParticipant` rings the project's number INTO the same
   room; the human who answers shares it with the caller, the attempt is one
   `supervisor.transfer` line with `mode=warm`, the ring respects `RINGING_S`,
   and once bridged the agent is muted — it never speaks again.

The LiveKit API is the same fake `test_transfer.py` uses, imported rather than
copied: an agent-initiated transfer and a desk-initiated one have to reach the
SFU through the same five methods or one of them is doing something else.
"""

import pytest
from livekit.agents.llm import ToolError, tool_context

from convo.agents.human import transfer_to_human
from convo.session import pipeline
from convo.state.store import MemoryStore, PipelineOverride
from convo.supervision.control import SupervisorControl
from convo.supervision.supervisor import TRANSFER
from convo.telephony import human, transfer
from convo.testing import fake_context
from tests.test_transfer import CALLER, ROOM, TRUNK, FakeAPI, FakeRoom, FakeSession, Person

pytestmark = pytest.mark.unit

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


# ── 1. a tool that cannot work is not offered ────────────────────────────────


def test_a_project_with_a_number_shows_the_verb_on_every_stage_of_the_call(tc) -> None:
    for stage in tc.project.stages(tc):
        assert human.TOOL in tool_names(stage), f"{stage.stage_name()} cannot hand the call on"


def test_a_project_with_no_number_never_shows_the_model_the_verb_at_all() -> None:
    shop = fake_context(*SHOP)

    for stage in shop.project.stages(shop):
        assert human.TOOL not in tool_names(stage)


def test_the_project_that_declares_no_spec_is_told_that_no_number_would_help(tc) -> None:
    assert human.unavailable(_without_the_spec(tc.project)) == human.NOT_DECLARED


def test_the_paragraph_that_teaches_the_verb_arrives_and_leaves_with_it(tc) -> None:
    shop = fake_context(*SHOP)

    assert human.protocol(tc.project) == human.PROTOCOL
    assert human.protocol(shop.project) == human.ALONE, "silence is not honesty"


def test_a_project_that_never_asked_the_question_is_told_nothing_about_transfers(tc) -> None:
    """Core invents no policy for a business that did not declare the verb."""
    tc.project = _without_the_spec(tc.project)

    assert human.protocol(tc.project) == ""


def test_the_clinic_prompt_teaches_the_announcement_and_the_shop_prompt_teaches_the_truth(
    tc,
) -> None:
    """A shop with nobody to pass a call to must not answer «ahora mismo te paso» (2026-08-31)."""
    shop = fake_context(*SHOP)
    clinic_prompt = tc.project.entry_agent(tc).instructions
    shop_prompt = shop.project.entry_agent(shop).instructions

    assert "le paso con un compañero" in clinic_prompt
    assert human.TOOL not in shop_prompt, "a rule about a tool it lacks makes it reach for one"
    assert "no hay nadie más a quien pasar la llamada" in shop_prompt


# ── 2. the console owns the number ───────────────────────────────────────────


def test_the_console_may_set_the_number_and_the_platform_says_which_ones_it_runs() -> None:
    assert pipeline.overridable(human.FIELD, SWITCHBOARD) is None
    assert pipeline.overridable(human.FIELD, "") is None, "empty takes the verb away"
    for bad in ("910000000", "+34 910 000 000", "recepción", "ext 204"):
        assert "E.164" in (pipeline.overridable(human.FIELD, bad) or "")


def test_the_pipeline_screen_shows_the_number_and_says_the_verb_is_live(tc) -> None:
    view = pipeline.snapshot(tc.tenant, tc.project, MemoryStore())["phone"]["transfer"]

    assert view["number"] == SWITCHBOARD
    assert view["offered"] is True
    assert view["unavailable_reasons"] == {}


def test_a_project_with_no_number_is_greyed_out_with_the_reason_in_the_servers_words() -> None:
    shop = fake_context(*SHOP)

    view = pipeline.snapshot(shop.tenant, shop.project, MemoryStore())["phone"]["transfer"]

    assert view["offered"] is False
    assert view["unavailable_reasons"] == {human.TOOL: human.NO_NUMBER}
    assert view["note"] == human.NO_NUMBER


async def test_clearing_the_number_from_the_console_takes_the_verb_off_the_next_session() -> None:
    from convo.state import overrides

    tc = fake_context(*CLINIC)
    store = MemoryStore()
    store.set_pipeline_override(PipelineOverride(tc.tenant.id, tc.project.id, human.FIELD, ""))

    cleared = overrides.apply(tc.tenant.id, tc.project, store)

    assert human.number_of(cleared) == ""
    assert human.offered(cleared) is False


# ── 3. on a phone call the verb REFERs the caller's own leg ──────────────────


async def test_a_caller_on_the_phone_is_referred_to_the_projects_own_number(tc, livekit) -> None:
    on_a_phone(tc)

    answered = await tc.tools.call(human.TOOL, {})

    (request,) = livekit.sip.transfers
    assert request.participant_identity == CALLER
    assert request.room_name == ROOM
    assert request.transfer_to == f"tel:{SWITCHBOARD}"
    assert answered["ok"] is True and answered["outcome"] == transfer.TRANSFERRED


async def test_the_attempt_is_one_supervisor_transfer_line_with_its_mode_and_outcome(
    tc, livekit
) -> None:
    on_a_phone(tc)

    await tc.tools.call(human.TOOL, {})

    (line,) = transfers(tc)
    assert line.payload["mode"] == transfer.COLD
    assert line.payload["outcome"] == transfer.TRANSFERRED
    assert line.payload["by"] == "agent", "an auditor reads WHO decided, and it was not a human"


async def test_the_agent_says_nothing_more_once_the_carrier_has_the_call(tc, livekit) -> None:
    on_a_phone(tc)

    said = human.said(await tc.tools.call(human.TOOL, {}))

    assert said == human.MOVED


async def test_the_platform_adds_no_hold_line_because_the_agent_announced_it_itself(
    tc, livekit
) -> None:
    """The model's own «le paso con un compañero» is the announcement; two is one too many."""
    control = on_a_phone(tc)

    await tc.tools.call(human.TOOL, {})

    assert control.session.said == []


# ── 4. a refused REFER is an answer, and the caller is still there ────────────


async def test_a_carrier_that_refuses_leaves_the_caller_on_the_line_and_says_so(
    tc, livekit
) -> None:
    on_a_phone(tc)
    livekit.sip.transfer_raises = _busy()

    answered = await tc.tools.call(human.TOOL, {})

    assert answered["ok"] is False and answered["outcome"] == transfer.BUSY
    said = human.said(answered)
    assert transfer.BUSY in said and "SIGUE contigo" in said


async def test_a_failed_transfer_is_logged_with_the_outcome_that_failed_it(tc, livekit) -> None:
    on_a_phone(tc)
    livekit.sip.transfer_raises = _busy()

    await tc.tools.call(human.TOOL, {})

    (line,) = transfers(tc)
    assert line.payload["ok"] is False and line.payload["outcome"] == transfer.BUSY


# ── 5. a chat, and a browser call this box cannot bridge, are told the truth ──


async def test_a_browser_call_with_no_trunk_is_refused_at_the_door_naming_the_variable(
    tc, livekit, monkeypatch
) -> None:
    """Never halfway through a call: no dial, no cut, and the log says what is missing."""
    monkeypatch.delenv(transfer.TRUNK_ENV, raising=False)
    in_a_browser(tc)

    with pytest.raises(ToolError) as refused:
        await tc.tools.call(human.TOOL, {})

    assert str(refused.value) == human.NO_BRIDGE
    assert livekit.sip.dials == [], "nobody's phone rang"
    assert livekit.room.subscriptions == [], "nobody was cut deaf for a bridge that never was"
    (line,) = transfers(tc)
    assert line.payload["mode"] == transfer.WARM
    assert transfer.TRUNK_ENV in line.payload["detail"]


async def test_a_chat_gets_the_same_honest_answer_and_offers_what_it_can(tc) -> None:
    """A chat has no room at all: `fake_context` is the eval harness's own shape."""
    with pytest.raises(ToolError) as refused:
        await tc.tools.call(human.TOOL, {})

    assert str(refused.value) == human.NO_PHONE_CALL
    assert "teléfono del centro" in human.NO_PHONE_CALL


async def test_a_channel_that_cannot_transfer_still_writes_the_attempt_down(tc) -> None:
    with pytest.raises(ToolError):
        await tc.tools.call(human.TOOL, {})

    (line,) = transfers(tc)
    assert line.payload["outcome"] == transfer.NO_LEG
    assert line.payload["to"] == SWITCHBOARD


def test_the_model_reads_a_docstring_that_tells_it_to_announce_first() -> None:
    described = tool_context.get_function_info(transfer_to_human)

    assert described.name == human.TOOL
    assert "le paso con un compañero" in (transfer_to_human.__doc__ or "")


# ── 6. a browser caller with a trunk gets the phone brought to them ──────────


async def test_a_browser_caller_gets_the_projects_number_dialled_into_their_own_room(
    tc, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    in_a_browser(tc)

    answered = await tc.tools.call(human.TOOL, {})

    (request,) = livekit.sip.dials
    assert request.sip_trunk_id == TRUNK
    assert request.sip_call_to == SWITCHBOARD
    assert request.room_name == ROOM, "the human joins the caller's room, not a new one"
    assert answered["ok"] is True and answered["outcome"] == transfer.BRIDGED
    assert livekit.sip.transfers == [], "a browser leg has nothing to REFER"


async def test_the_warm_ring_respects_the_deployments_ringing_budget(
    tc, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    in_a_browser(tc)

    await tc.tools.call(human.TOOL, {})

    (request,) = livekit.sip.dials
    assert request.ringing_timeout.seconds == int(transfer.RINGING_S)


async def test_a_warm_attempt_is_one_log_line_with_mode_warm_and_the_real_outcome(
    tc, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    in_a_browser(tc)

    await tc.tools.call(human.TOOL, {})

    (line,) = transfers(tc)
    assert line.payload["mode"] == transfer.WARM
    assert line.payload["outcome"] == transfer.BRIDGED
    assert line.payload["by"] == "agent"
    assert line.payload["ok"] is True


async def test_the_agent_reads_that_the_colleague_is_arriving_and_says_nothing_more(
    tc, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    in_a_browser(tc)

    said = human.said(await tc.tools.call(human.TOOL, {}))

    assert said == human.JOINED


async def test_a_bridged_browser_call_leaves_the_agent_muted_so_it_is_not_a_third_voice(
    tc, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    control = in_a_browser(tc)

    await tc.tools.call(human.TOOL, {})

    assert control.muted is True


async def test_a_colleague_who_does_not_pick_up_leaves_the_caller_with_the_agent(
    tc, livekit, monkeypatch
) -> None:
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    control = in_a_browser(tc)
    livekit.sip.dial_raises = _busy()

    answered = await tc.tools.call(human.TOOL, {})

    assert answered["ok"] is False and answered["outcome"] == transfer.BUSY
    assert control.muted is False, "nobody arrived, so the agent keeps the line"
    assert "SIGUE contigo" in human.said(answered)


async def test_a_phone_caller_still_gets_a_refer_even_with_the_trunk_configured(
    tc, livekit, monkeypatch
) -> None:
    """The trunk arms the browser branch and changes nothing for PSTN."""
    monkeypatch.setenv(transfer.TRUNK_ENV, TRUNK)
    on_a_phone(tc)

    answered = await tc.tools.call(human.TOOL, {})

    assert livekit.sip.transfers and livekit.sip.dials == []
    assert answered["mode"] == transfer.COLD


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
