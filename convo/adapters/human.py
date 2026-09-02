"""The platform's own adapter: the system on the other side of this one is the carrier.

Decisions: docs/decisions/convo.adapters.human.md
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
        """Transfer the call, or refuse it honestly; either way one log line says which."""
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
        """The browser branch: dial the human INTO the room — the phone comes to the caller."""
        try:
            return await hand.join(to)
        except TransferRefused as refused:
            self._record(Outcome(WARM, to, UNREACHABLE, ok=False, detail=str(refused)))
            raise ToolError(human.NO_BRIDGE) from refused

    async def _fall_silent(self) -> None:
        """A bridged call has a human on it: the agent mutes itself and never speaks again."""
        control = getattr(self.tc, "supervisor", None)
        if control is not None:
            await control.takeover(BY_THE_AGENT)

    def _handover(self) -> Handover | None:
        """The transfer's view of this session, or None where there is no room to transfer in."""
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
