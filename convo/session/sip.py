"""The SIP caller: the attributes `livekit-sip` hangs on the participant it created.

Decisions: docs/decisions/convo.session.sip.md
"""

import asyncio
import logging
import os
from typing import Any

WAIT_ENV = "SIP_WAIT_S"
DEFAULT_WAIT_S = 5.0
NUMBER_ATTRS = ("sip.trunkPhoneNumber", "sip.phoneNumber")
PREFIX = "sip."

log = logging.getLogger("platform.sip")


async def caller_attributes(ctx: Any, wait_s: float | None = None) -> dict[str, str]:
    """Every `sip.*` attribute of this job's caller, or `{}` when the job is not a call."""
    direct = _sip_only(_attributes_of(getattr(ctx.job, "participant", None)))
    if direct:
        return direct
    room = getattr(ctx, "room", None)
    if room is None:
        return {}
    present = _sip_only(_attributes_of(_sip_participant(room)))
    if present:
        return present
    return _sip_only(_attributes_of(await _await_sip_participant(ctx, wait_s)))


def dialled_number(attributes: dict[str, str]) -> str | None:
    """The number the caller dialled — the key the routes table is read by."""
    for name in NUMBER_ATTRS:
        if attributes.get(name):
            return attributes[name]
    return None


def wait_budget() -> float:
    """How long to wait for a SIP participant that has not joined yet (`SIP_WAIT_S`)."""
    try:
        return float(os.getenv(WAIT_ENV, "") or DEFAULT_WAIT_S)
    except ValueError:
        return DEFAULT_WAIT_S


def _sip_participant(room: Any) -> Any | None:
    """The first participant in the room whose attributes carry `sip.*`, if any."""
    remotes = getattr(room, "remote_participants", None) or {}
    for participant in list(remotes.values()):
        if _sip_only(_attributes_of(participant)):
            return participant
    return None


async def _await_sip_participant(ctx: Any, wait_s: float | None) -> Any | None:
    """Wait, briefly, for the caller to appear; nothing arriving is an answer too."""
    budget = wait_budget() if wait_s is None else wait_s
    waiter = getattr(ctx, "wait_for_participant", None)
    if waiter is None or budget <= 0:
        return None
    try:
        from livekit import rtc

        kind = rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        return await asyncio.wait_for(waiter(kind=kind), budget)
    except TimeoutError:
        return None
    except Exception:
        log.debug("no SIP participant for this job", exc_info=True)
        return None


def _attributes_of(participant: Any | None) -> dict[str, str]:
    """A participant's attributes as a plain dict (the proto map is not one)."""
    return dict(getattr(participant, "attributes", None) or {})


def _sip_only(attributes: dict[str, str]) -> dict[str, str]:
    """Just the `sip.*` keys: everything else on a participant belongs to somebody else."""
    return {key: value for key, value in attributes.items() if key.startswith(PREFIX)}
