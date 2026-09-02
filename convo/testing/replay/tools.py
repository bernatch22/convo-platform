"""The tool half of a replayed session: `tool.*` events paired back into `ToolCall`s.

Decisions: docs/decisions/convo.testing.replay.tools.md
"""

from collections.abc import Mapping

from deepeval.test_case import ToolCall

from convo.state.events import Event

CALL_KINDS = ("tool.call", "tool.refused")
RESULT_KINDS = ("tool.result", "tool.error")

NO_PAYLOAD = (
    "this tool declares no result summary, so the log kept the shape of what it "
    "returned and not its contents (PII) — what this call returned is not available here"
)
REFUSED = "refused before it ran ({reason}) — nothing was written"
FAILED = "the call failed ({key}) and nothing usable came back"


def missing_tool_outputs(case) -> list[str]:
    """The tools whose result a grounding metric cannot see, once each, in order."""
    names: list[str] = []
    for turn in case.turns:
        for call in turn.tools_called or []:
            blind = call.output is None or NO_PAYLOAD in str(call.output)
            if blind and call.name not in names:
                names.append(call.name)
    return names


class Calls:
    """The tool calls seen since the last assistant turn, paired with their results."""

    def __init__(self, descriptions: Mapping[str, str] | None) -> None:
        self.descriptions = descriptions or {}
        self.calls: list[ToolCall] = []
        self.open: dict[str, list[int]] = {}

    def record(self, event: Event) -> None:
        """One tool event: a call opens a ToolCall, a result or an error closes it."""
        tool = str(event.payload.get("tool", "?"))
        if event.kind in RESULT_KINDS:
            self._close(tool, event)
            return
        self.calls.append(
            ToolCall(
                name=tool,
                description=self.descriptions.get(tool),
                input_parameters=dict(event.payload.get("args") or {}),
                output=self._refusal(event),
            )
        )
        if event.kind == "tool.call":
            self.open.setdefault(tool, []).append(len(self.calls) - 1)

    def take(self) -> list[ToolCall] | None:
        """Everything since the last take, and start counting the next turn."""
        calls, self.calls, self.open = self.calls, [], {}
        return calls or None

    def _close(self, tool: str, event: Event) -> None:
        """Give the oldest unanswered call of that name its outcome; a stray result is dropped."""
        waiting = self.open.get(tool) or []
        if not waiting:
            return  # the call was on a previous turn, or the log starts mid-call
        self.calls[waiting.pop(0)].output = self._outcome(event)

    def _outcome(self, event: Event) -> str:
        """What the judge is told this call returned: its summary, or why there is none."""
        if event.kind == "tool.error":
            return FAILED.format(key=event.payload.get("key", "unknown"))
        summary = str(event.payload.get("summary") or "").strip()
        if summary:
            return summary
        return f"{event.payload.get('shape', 'unknown')} — {NO_PAYLOAD}"

    def _refusal(self, event: Event) -> str | None:
        if event.kind != "tool.refused":
            return None
        return REFUSED.format(reason=event.payload.get("reason", "no reason recorded"))
