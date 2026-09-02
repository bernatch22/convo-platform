"""The turn half of a replayed session: `turn.*` events read back as DeepEval `Turn`s.

Decisions: docs/decisions/convo.testing.replay.turns.md
"""

from collections.abc import Mapping

from deepeval.test_case import Turn

from convo.state.events import Event
from convo.testing.replay.tools import CALL_KINDS, RESULT_KINDS, Calls

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
    """Calls that ran after the last thing anybody said still belong to the call."""
    if not calls:
        return
    for turn in reversed(turns):
        if turn.role == "assistant":
            turn.tools_called = (turn.tools_called or []) + calls
            return
    turns.append(Turn(role="assistant", content="", tools_called=calls))


def _text(event: Event) -> str:
    return str(event.payload.get("text") or "")
