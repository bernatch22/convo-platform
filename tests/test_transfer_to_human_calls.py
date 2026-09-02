"""transfer_to_human on a phone, in a browser and in a chat: what each channel can honestly do."""

import pytest
from livekit.agents.llm import ToolError, tool_context

from convo.agents.human import transfer_to_human
from convo.telephony import human, transfer
from tests.fixtures.handover import (  # noqa: F401  (fixtures)
    SWITCHBOARD,
    _busy,
    in_a_browser,
    livekit,
    on_a_phone,
    tc,
    transfers,
)
from tests.fixtures.transfer import CALLER, ROOM, TRUNK

pytestmark = pytest.mark.unit


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
