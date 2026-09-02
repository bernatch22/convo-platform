"""The platform's own adapter: the system on the other side of this one is the carrier.

Every other adapter in this codebase belongs to a tenant — an agenda, an order
book, an SMS gateway. This one belongs to the platform, and it is an adapter
rather than a special case in the executor for one reason: a transfer is a
WRITE, and everything the platform promises about a write must apply to it. The
catalog says whether the project may call it, `guard.check` vets it, the
timeout is the spec's, the failure sentence is the project's, and both halves
of the attempt land in the session log — `tool.call`/`tool.result` like any
other tool, and one `supervisor.transfer` line carrying the mode and the
outcome, the same vocabulary a supervisor's transfer writes (ms-15).

It is attached to every context by `core.tools.attach_local_tools`, next to the
tenant's own adapters, and it is reachable only by a project that declares
`transfer_to_human` in its catalog. A project that does not is exactly where it
was before this file existed.

The one judgement it makes is what kind of call this is, and each kind gets
the honest mechanism. A PSTN caller has a SIP leg, so a REFER moves it to the
colleague. A browser caller has none — so the phone comes to THEM: a warm
bridge dials the colleague INTO the room (`Handover.join`), refused at the
door when the box has no outbound trunk. A chat has no audio to join at all,
so it keeps the refusal it always had. Every branch writes the attempt down,
and the two refusals never touch the SFU.
"""

import logging
from typing import TYPE_CHECKING, Any

from livekit.agents.llm import ToolError

from convo.adapters.base import Adapter
from convo.state.log import record
from convo.supervision.supervisor import TRANSFER
from convo.telephony import human
from convo.telephony.handover import Handover
from convo.telephony.transfer import (
    COLD,
    NO_LEG,
    UNREACHABLE,
    WARM,
    Outcome,
    TransferRefused,
)

if TYPE_CHECKING:  # the context carries the adapters, so it cannot be imported at runtime
    from convo.domain.context import TenantContext

log = logging.getLogger("platform.telephony")

# Who caused this transfer, in the log line. A supervisor's carries their signed
# `sup:` identity; the agent has none to carry, and "the agent decided" is the
# fact an auditor is reading the line for.
BY_THE_AGENT = "agent"


class HumanTransfer(Adapter):
    """Hands the live call to the project's `transfer_number`, and writes down what happened."""

    def __init__(self, tc: "TenantContext") -> None:
        self.tc = tc

    def capabilities(self) -> list[str]:
        """The one capability this adapter has: moving the caller to a person."""
        return [human.TOOL]

    async def execute(self, capability: str, args: dict[str, Any]) -> dict[str, Any]:
        """Transfer the call, or refuse it honestly; either way one log line says which.

        → the `Outcome` payload (`mode`, `outcome`, `to`, `ok`, …), which
        `core.agents.human` turns into the sentence the model acts on. `ok=False`
        is an ANSWER and not an exception: the caller is still on the line and
        somebody has to speak to them.

        `ToolError` is raised for the cases where nothing was even attempted —
        no number, no call to move, a warm bridge this box cannot dial — because
        the model must read those as "this did not happen" and not as a
        transfer that failed.
        """
        to = human.number_of(self.tc.project)
        if not to:
            raise ToolError(human.NO_PHONE_CALL)
        hand = self._handover()
        if hand is None or self.tc.channel != "voice":
            self._record(Outcome(COLD, to, NO_LEG, ok=False, detail=self.tc.channel))
            raise ToolError(human.NO_PHONE_CALL)
        outcome = await (self._refer(hand, to) if hand.on_a_phone() else self._join(hand, to))
        self._record(outcome)
        if outcome.ok and outcome.mode == WARM:
            await self._fall_silent()
        return outcome.as_payload()

    async def _refer(self, hand: Handover, to: str) -> Outcome:
        """The PSTN branch: REFER the caller's own leg — the carrier takes the call."""
        try:
            return await hand.refer(to)
        except TransferRefused as refused:
            self._record(Outcome(COLD, to, NO_LEG, ok=False, detail=str(refused)))
            raise ToolError(human.NO_PHONE_CALL) from refused

    async def _join(self, hand: Handover, to: str) -> Outcome:
        """The browser branch: dial the human INTO the room — the phone comes to the caller.

        `TransferRefused` here is the door doing its job — on this box almost
        always "no `SIP_OUTBOUND_TRUNK_ID`" — so the refusal is logged with the
        sentence that names the variable, nobody's phone has rung, and the
        model reads an honest "this cannot be done right now".
        """
        try:
            return await hand.join(to)
        except TransferRefused as refused:
            self._record(Outcome(WARM, to, UNREACHABLE, ok=False, detail=str(refused)))
            raise ToolError(human.NO_BRIDGE) from refused

    async def _fall_silent(self) -> None:
        """A bridged call has a human on it: the agent mutes itself and never speaks again.

        The same `takeover` a supervisor's warm transfer ends in
        (`core.security.control`), so the audit shows the mute and a later
        `release` from the desk could hand the line back the same way.
        """
        control = getattr(self.tc, "supervisor", None)
        if control is not None:
            await control.takeover(BY_THE_AGENT)

    def _handover(self) -> Handover | None:
        """The transfer's view of this session, or None where there is no room to transfer in.

        The room and the session hang on `SupervisorControl`, built in
        `worker.py` with the job's own room — the same two things a supervisor's
        transfer uses, read from the same place, so an agent-initiated transfer
        and a desk-initiated one cannot disagree about which call they are
        moving. A console run and the eval harness have no control at all, which
        is the honest answer that they have no call to move either.
        """
        control = getattr(self.tc, "supervisor", None)
        room = getattr(control, "room", None)
        if control is None or room is None:
            return None
        return Handover(self.tc, getattr(control, "session", None), room)

    def _record(self, outcome: Outcome) -> None:
        """One `supervisor.transfer` line in the caller's own log, mode and outcome first."""
        record(self.tc, TRANSFER, {"by": BY_THE_AGENT, **outcome.as_payload()})
        log.info(
            "agent transferred %s to %s: %s (%s)",
            self.tc.label(),
            outcome.to,
            outcome.outcome,
            outcome.mode,
        )
