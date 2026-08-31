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

The one judgement it makes is `on_a_phone`: a REFER moves a phone leg, and a
browser call or a chat has none. That is not a failure to report, it is a
question to answer honestly and early — so it never touches the SFU, it writes
the attempt down all the same, and it raises the sentence the model reads out
in its own words.
"""

import logging
from typing import TYPE_CHECKING, Any

from livekit.agents.llm import ToolError

from core.adapters.base import Adapter
from core.security.supervisor import TRANSFER
from core.state.log import record
from core.telephony import human
from core.telephony.handover import Handover
from core.telephony.transfer import COLD, NO_LEG, Outcome, TransferRefused

if TYPE_CHECKING:  # the context carries the adapters, so it cannot be imported at runtime
    from core.context import TenantContext

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

        `ToolError` is raised for the two cases where nothing was even
        attempted — no number, and no phone leg to move — because the model must
        read those as "this did not happen" and not as a transfer that failed.
        """
        to = human.number_of(self.tc.project)
        if not to:
            raise ToolError(human.NO_PHONE_CALL)
        hand = self._handover()
        if hand is None or not hand.on_a_phone():
            self._record(Outcome(COLD, to, NO_LEG, ok=False, detail=self.tc.channel))
            raise ToolError(human.NO_PHONE_CALL)
        try:
            outcome = await hand.refer(to)
        except TransferRefused as refused:
            self._record(Outcome(COLD, to, NO_LEG, ok=False, detail=str(refused)))
            raise ToolError(human.NO_PHONE_CALL) from refused
        self._record(outcome)
        return outcome.as_payload()

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
