"""The turn half of a replayed session: `turn.*` events read back as DeepEval `Turn`s.

The turns are `turn.user` and `turn.agent` in seq order, and the tool events
between two agent turns hang from the **following** assistant turn: Haiku says
"un momento, le consulto la agenda", the tools run, and the answer is what they
produced. Pairing those tool events into calls is `tools.py`; this module only
decides which turn each batch belongs to.

Pure and model-free: hand `turns_from` a list of events and it hands back
turns, which is how the conversion is tested without spending a cent.
"""

from collections.abc import Mapping

from deepeval.test_case import Turn

from core.state.events import Event
from core.testing.replay.tools import CALL_KINDS, RESULT_KINDS, Calls

TURN_KINDS = {"turn.user": "user", "turn.agent": "assistant"}


def turns_from(
    events: list[Event],
    descriptions: Mapping[str, str] | None = None,
) -> list[Turn]:
    """The log's turns, in seq order, each assistant turn carrying what it ran."""
    turns: list[Turn] = []
    pending = Calls(descriptions)
    for event in events:
        role = TURN_KINDS.get(event.kind)
        if role == "user":
            turns.append(Turn(role="user", content=_text(event)))
        elif role == "assistant":
            turns.append(Turn(role="assistant", content=_text(event), tools_called=pending.take()))
        elif event.kind in CALL_KINDS + RESULT_KINDS:
            pending.record(event)
    _attach_trailing(turns, pending.take())
    return turns


def _attach_trailing(turns: list[Turn], calls: list | None) -> None:
    """Calls that ran after the last thing anybody said still belong to the call.

    A booking whose SMS went out while the agent was already hanging up, or a
    session killed after its last reply, leaves tool events with no turn after
    them. They go on the last assistant turn — and if the call has no assistant
    turn at all, on a silent one, because dropping them would hide the only
    record that the customer's system was written to.
    """
    if not calls:
        return
    for turn in reversed(turns):
        if turn.role == "assistant":
            turn.tools_called = (turn.tools_called or []) + calls
            return
    turns.append(Turn(role="assistant", content="", tools_called=calls))


def _text(event: Event) -> str:
    return str(event.payload.get("text") or "")
