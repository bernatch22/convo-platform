"""The two ways a live call leaves this agent for a human: cold REFER, warm dial-in.

**Cold** is one API call. `TransferSIPParticipant` makes `livekit-sip` send a
SIP REFER on the caller's own leg; the carrier takes the call from there, the
caller leaves the room and this job ends. It is the whole of a blind transfer
and it needs nothing but a trunk that accepts REFER.

**Warm** is hand-rolled, and it is hand-rolled for a reason that was measured
rather than read: `MoveParticipant` — the RPC the framework's own
`WarmTransferTask` is built on — answers `twirp error unknown: not
implemented` on this server, so the supported path does not exist here. What
does exist is `CreateSIPParticipant`, which dials a phone INTO the caller's
room, and `core.telephony.isolation`, which makes the briefing inaudible to
the caller while it happens. Those two are enough.

**A failed transfer must leave the caller where they were.** That is the
difference between an outcome and an accident, and it is why every failure
below comes back as an `Outcome` with `ok=False` and a SIP status rather than
an exception: the agent has to say something to somebody who is still on the
line. `SipCallError.sip_status_code` is what makes that sentence specific — a
486 is "he is on another call", a 603 on this trunk is very nearly always "the
carrier refused the REFER", which is a deployment fault and not the caller's.

What warm needs and this deployment does not yet have: an **outbound**
(termination) trunk. `infra/box/README.md` says it plainly — the box's Twilio
trunk has Origination and no Termination, so there is no id to put in
`SIP_OUTBOUND_TRUNK_ID` and dialling out is refused at the door with
`TransferRefused` instead of failing halfway through a call. Creating that
trunk is a deliberate, human, out-of-band act (see the fraud checklist), not
something this module does on the fly.

Open source note: the whole file is tenant-free and framework-free — it talks
to `livekit.api` and nothing else. A stranger gets cold and warm transfer for
any self-hosted LiveKit SIP deployment by copying this and `isolation.py`.
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from livekit import api
from livekit.protocol.sip import SIPTransferStatus

from core.telephony import isolation

log = logging.getLogger("platform.telephony")

COLD = "cold"
WARM = "warm"
MODES: tuple[str, ...] = (COLD, WARM)

# What a transfer ENDED as — the second half of every `supervisor.transfer` log line.
TRANSFERRED = "transferred"  # cold: the carrier took the call, the caller is gone
ONGOING = "ongoing"  # cold: the REFER was accepted and the outcome never came back
BRIDGED = "bridged"  # warm: the human and the caller are hearing each other
NO_ANSWER = "no_answer"  # the phone rang out
BUSY = "busy"  # the phone was on another call
REJECTED = "rejected"  # somebody said no: the person, or the carrier
UNREACHABLE = "unreachable"  # the SFU or the trunk could not be asked at all
NO_LEG = "no_phone_leg"  # there was no phone call to move: a browser or a chat asked

# The SIP response code, turned into a word an operator can act on.
SIP_OUTCOMES: dict[int, str] = {
    403: REJECTED,
    404: REJECTED,
    405: REJECTED,
    408: NO_ANSWER,
    480: NO_ANSWER,
    486: BUSY,
    487: NO_ANSWER,
    488: REJECTED,
    503: UNREACHABLE,
    600: BUSY,
    603: REJECTED,
    604: REJECTED,
    606: REJECTED,
}

# The one code worth a sentence of its own. Twilio documents NO SIP response for
# a REFER it refuses — the whole `call-transfer` page contains exactly two codes,
# both `202`. That 603 means "this trunk will not transfer" is field evidence
# (livekit/sip#234, same setup, closed with no published diagnosis), so the hint
# says where to look and does not claim to know.
DECLINED_HINT = (
    "603: Twilio documents no response code for a refused REFER, but this is the "
    "reported symptom of TransferMode != enable-all — check the trunk "
    "(infra/box/README.md, 'Call transfer')"
)

# How long the far end may ring before the transfer is given up on. LiveKit's own
# default is 30 s; a caller on hold notices 30 s, so this deployment rings for less.
RINGING_S = float(os.getenv("TRANSFER_RINGING_S", "") or 25.0)

# The outbound trunk a warm leg dials through; empty means this box cannot dial out.
TRUNK_ENV = "SIP_OUTBOUND_TRUNK_ID"

# Where a transfer goes when the desk names no number — the demo's one mobile.
TARGET_ENV = "TRANSFER_TO"

# The identity a dialled-in human gets, so `is_supervisor` and the router both ignore them.
HUMAN_PREFIX = "human:"


class TransferRefused(RuntimeError):
    """The transfer was refused before anything was dialled — nothing happened to the call."""


@dataclass(frozen=True)
class Outcome:
    """What a transfer did, in the words the log and the agent both use."""

    mode: str
    to: str
    outcome: str
    ok: bool
    sip_status: int | None = None
    detail: str = ""
    participant: str = ""
    cut: list[str] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        """The `supervisor.transfer` payload: mode and outcome first, because that is the audit."""
        payload: dict[str, Any] = {
            "mode": self.mode,
            "outcome": self.outcome,
            "to": self.to,
            "ok": self.ok,
        }
        if self.sip_status is not None:
            payload["sip_status"] = self.sip_status
        if self.detail:
            payload["detail"] = self.detail
        if self.participant:
            payload["participant"] = self.participant
        return payload


async def cold(client: api.LiveKitAPI, room: str, caller: str, to: str) -> Outcome:
    """REFER the caller's leg to a phone: the carrier takes the call and this job ends.

    → an `Outcome`. `ok=False` always means the caller is STILL IN THE ROOM,
    which is the only reason this returns instead of raising: somebody is
    waiting to be spoken to.
    """
    target = dial_uri(to)
    request = api.TransferSIPParticipantRequest(
        participant_identity=caller, room_name=room, transfer_to=target, play_dialtone=True
    )
    request.ringing_timeout.FromSeconds(int(RINGING_S))
    log.info("cold transfer of %s in %s to %s", caller, room, target)
    try:
        answer = await client.sip.transfer_sip_participant(request)
    except api.SipCallError as refused:
        return _refused(COLD, to, refused)
    except Exception as error:  # noqa: BLE001 — a dead SFU is an outcome, not a crash
        log.exception("cold transfer to %s failed", target)
        return Outcome(COLD, to, UNREACHABLE, ok=False, detail=str(error))
    return _answered(to, answer)


class WarmLeg:
    """The human's leg of a warm transfer: dialled into the caller's room, and inaudible to them.

    Three moves, in this order and only this order: `dial` brings the human in
    with the caller already cut off, `bridge` opens the three-way, and
    `hang_up` undoes everything when the briefing decides against the transfer.
    Each returns an `Outcome`, and a failed `dial` has already restored the
    caller's audio before it returns.
    """

    def __init__(self, client: api.LiveKitAPI, room: str, caller: str, to: str) -> None:
        # Both of these raise `TransferRefused`, and they raise HERE on purpose:
        # a leg that can never be dialled must be refused before the caller has
        # been told to hold and before a single subscription has been cut.
        self.trunk = outbound_trunk()
        self.number = phone_number(to)
        self.client = client
        self.room = room
        self.caller = caller
        self.to = to
        self.identity = f"{HUMAN_PREFIX}{uuid.uuid4().hex[:8]}"
        self.cut: list[str] = []

    async def dial(self, silenced: list[str]) -> Outcome:
        """Ring the human and cut them out of the caller's ears the instant they answer.

        `silenced` is what the choreography cut BEFORE dialling — the agent's
        own track — so that a failure here can put it all back in one place.
        """
        target = self.number
        request = api.CreateSIPParticipantRequest(
            sip_trunk_id=self.trunk,
            sip_call_to=target,
            room_name=self.room,
            participant_identity=self.identity,
            participant_name="colega",
            participant_attributes={"role": "human", "transfer": WARM},
            play_dialtone=False,
            wait_until_answered=True,
            krisp_enabled=False,
        )
        request.ringing_timeout.FromSeconds(int(RINGING_S))
        log.info("warm leg: dialling %s into %s as %s", target, self.room, self.identity)
        try:
            await self.client.sip.create_sip_participant(request)
        except api.SipCallError as refused:
            await self._restore(silenced)
            return _refused(WARM, self.to, refused, participant=self.identity)
        except Exception as error:  # noqa: BLE001 — see `cold`
            log.exception("warm leg to %s failed", target)
            await self._restore(silenced)
            return Outcome(WARM, self.to, UNREACHABLE, ok=False, detail=str(error))
        # The colleague's track exists only once they answer, so this is the
        # earliest the cut can be made — and the cut itself takes ~220 ms to
        # bite (measured, `scripts/isolation_probe.py`). That window is this
        # design's one residual: about a fifth of a second of the colleague's
        # first word can reach the caller. It cannot be closed from here —
        # there is no "subscribe to nothing new" on a participant — so it is
        # documented rather than hidden, and it is one more reason the agent's
        # own track is cut BEFORE the dial, where the ringing absorbs it.
        self.cut = silenced + await isolation.cut(
            self.client, self.room, self.caller, [self.identity]
        )
        return Outcome(WARM, self.to, "briefing", ok=True, participant=self.identity, cut=self.cut)

    async def bridge(self) -> Outcome:
        """Open the caller's ears again: the three of them are now on one call."""
        await isolation.restore(self.client, self.room, self.caller, self.cut)
        log.info("warm leg: %s bridged with %s in %s", self.identity, self.caller, self.room)
        return Outcome(WARM, self.to, BRIDGED, ok=True, participant=self.identity)

    async def hang_up(self, outcome: str = REJECTED, detail: str = "") -> Outcome:
        """Drop the human and give the caller their audio back — the briefing said no."""
        request = api.RoomParticipantIdentity(room=self.room, identity=self.identity)
        try:
            await self.client.room.remove_participant(request)
        except Exception as error:  # noqa: BLE001 — the leg may already be gone
            log.debug("warm leg %s was already gone: %s", self.identity, error)
        await self._restore(self.cut)
        return Outcome(WARM, self.to, outcome, ok=False, detail=detail, participant=self.identity)

    async def _restore(self, sids: list[str]) -> None:
        try:
            await isolation.restore(self.client, self.room, self.caller, sids)
        except Exception:  # noqa: BLE001 — a caller left deaf is worse than a noisy log
            log.exception("could not give %s their audio back in %s", self.caller, self.room)


def dial_uri(to: str) -> str:
    """`tel:+34…` for a phone number; a `sip:` or `tel:` URI is passed through untouched."""
    target = (to or "").strip()
    if not target:
        raise TransferRefused("a transfer with no destination goes nowhere")
    if target.startswith(("tel:", "sip:", "sips:")):
        return target
    if not target.startswith("+") or not target[1:].isdigit():
        raise TransferRefused(f"{to!r} is not an E.164 number (+34600111222) nor a SIP URI")
    return f"tel:{target}"


def destination(to: str) -> str:
    """Where this transfer goes: what the desk asked for, else the deployment's `TRANSFER_TO`.

    The number is deployment data, not core's: a desk that names one wins, and
    the env var exists so the demo has a mobile to ring without one.
    """
    return ((to or "").strip() or os.getenv(TARGET_ENV, "").strip()).strip()


def phone_number(to: str) -> str:
    """E.164 only — what an outbound trunk dials. A `sip:` URI is a cold-transfer target.

    `CreateSIPParticipant` takes a number, not a URI: a SIP destination needs
    `sip_request_uri` and a trunk configured for it, which is a different
    deployment and not something to guess at mid-call.
    """
    target = dial_uri(to)
    if not target.startswith("tel:"):
        raise TransferRefused(f"{to!r} is a SIP URI: a warm leg dials E.164 numbers only")
    return target.removeprefix("tel:")


def outbound_trunk() -> str:
    """The trunk a warm leg dials out through, or a refusal naming what is missing."""
    trunk = os.getenv(TRUNK_ENV, "").strip()
    if not trunk:
        raise TransferRefused(
            f"{TRUNK_ENV} is unset: this box has no outbound (termination) trunk, "
            "so a warm transfer cannot dial the human. Cold transfer needs none."
        )
    return trunk


def _answered(to: str, answer: Any) -> Outcome:
    """Read the server's own verdict — a 200 with `STS_TRANSFER_FAILED` is still a failure."""
    status = getattr(answer, "status", SIPTransferStatus.STS_TRANSFER_ONGOING)
    code = int(getattr(getattr(answer, "sip_status", None), "code", 0) or 0) or None
    if status == SIPTransferStatus.STS_TRANSFER_SUCCESSFUL:
        return Outcome(COLD, to, TRANSFERRED, ok=True, sip_status=code)
    if status == SIPTransferStatus.STS_TRANSFER_ONGOING:
        return Outcome(COLD, to, ONGOING, ok=True, sip_status=code)
    outcome = SIP_OUTCOMES.get(code or 0, REJECTED)
    return Outcome(COLD, to, outcome, ok=False, sip_status=code, detail=_hint(code))


def _refused(mode: str, to: str, refused: Any, participant: str = "") -> Outcome:
    """A `SipCallError` as an outcome: the code names it, and the caller never moved."""
    code = getattr(refused, "sip_status_code", None)
    outcome = SIP_OUTCOMES.get(code or 0, REJECTED)
    detail = _hint(code) or (getattr(refused, "sip_status", None) or str(refused))
    log.warning("%s transfer to %s refused: %s %s", mode, to, code, detail)
    return Outcome(
        mode, to, outcome, ok=False, sip_status=code, detail=detail, participant=participant
    )


def _hint(code: int | None) -> str:
    return DECLINED_HINT if code == 603 else ""
