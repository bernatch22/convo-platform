"""observe: subscribe one AgentSession's events to the session's append-only log.

The framework already emits everything an audit needs — a turn with its
latencies, a final transcript, the agent's state, the batch of tools that ran,
an error, the close and its reason. This module is the one place that knows
those names, so the log keeps its own vocabulary (`turn.agent`, `stt.final`,
`session.end`) and swapping the runtime is a change to this file alone.

What it deliberately does NOT do: log each tool call. The executor already
writes `tool.call` / `tool.result` with the arguments masked by `pii_scope`,
and it is the only place that knows which argument is a DNI. Here a batch of
tools is one line with a count, never the arguments again.

Every handler is synchronous and swallows nothing: LiveKit's emitter calls
them inline, so a slow or raising observer would sit in the audio path. They
do one dict and one append each.

Open source note: `observe(session, tc)` needs only `tc.log`; a fork that
keeps its events elsewhere replaces `EventLog` and nothing here changes.
"""

import logging
from typing import Any

from core.observability.prices import session_cost
from core.observability.voice import recording_path

log = logging.getLogger("platform.observers")

# Which of the framework's per-turn latencies reach the log. The rest
# (playback_latency, provider ids, the *_metadata blocks) belong to a trace,
# not to an audit line an operator reads in a terminal.
TURN_METRICS = (
    "transcription_delay",
    "end_of_turn_delay",
    "llm_node_ttft",
    "tts_node_ttfb",
    "e2e_latency",
)

# CloseReason -> the outcome a session row carries.
OUTCOMES = {
    "error": "error",
    "participant_disconnected": "dropped",
    "job_shutdown": "dropped",
    "user_initiated": "completed",
    "task_completed": "completed",
}

ROLE_KINDS = {"user": "turn.user", "assistant": "turn.agent"}


def observe(session, tc) -> None:
    """Wire one session's events into `tc.log`; a context without a log is left alone."""
    if getattr(tc, "log", None) is None:
        return
    observer = SessionObserver(session, tc)
    for event, handler in observer.handlers().items():
        session.on(event, handler)


class SessionObserver:
    """Holds the session and its context so each handler is one line of translation."""

    def __init__(self, session, tc) -> None:
        self.session = session
        self.tc = tc

    def handlers(self) -> dict[str, Any]:
        """The framework's event names mapped to the methods that record them."""
        return {
            "conversation_item_added": self.on_conversation_item_added,
            "user_input_transcribed": self.on_user_input_transcribed,
            "agent_state_changed": self.on_agent_state_changed,
            "function_tools_executed": self.on_function_tools_executed,
            "error": self.on_error,
            "close": self.on_close,
        }

    def on_conversation_item_added(self, event) -> None:
        """One turn: who spoke, what they said, and the latencies the framework measured."""
        kind = ROLE_KINDS.get(getattr(event.item, "role", None) or "")
        if kind is None:
            return  # a handoff marker or an item type we do not audit as a turn
        payload: dict[str, Any] = {"text": event.item.text_content or ""}
        metrics = turn_metrics(getattr(event.item, "metrics", None))
        if metrics:
            payload["metrics"] = metrics
        self._append(kind, payload)

    def on_user_input_transcribed(self, event) -> None:
        """Only the final transcript: interim hypotheses are noise in an audit log."""
        if not event.is_final:
            return
        self._append("stt.final", {"text": event.transcript, "language": event.language})

    def on_agent_state_changed(self, event) -> None:
        """listening / thinking / speaking — where the silence went on a slow call."""
        self._append("state", {"from": event.old_state, "to": event.new_state})

    def on_function_tools_executed(self, event) -> None:
        """How many tools that turn ran; the executor already logged each one, masked."""
        self._append("tools.executed", {"count": len(event.function_calls)})

    def on_error(self, event) -> None:
        """A provider failed. The message is a developer's, never a caller's."""
        self._append("error", {"source": type(event.source).__name__, "error": repr(event.error)})

    def on_close(self, event) -> None:
        """The envelope closes: why the call ended, what it cost, and where its audio is."""
        payload = {
            "outcome": outcome_of(event),
            "reason": str(getattr(event.reason, "value", event.reason)),
            "cost": session_cost(self.session.usage),
        }
        audio = recording_path(self.session)
        if audio:
            payload["audio"] = audio
        self._append("session.end", payload)

    def _append(self, kind: str, payload: dict[str, Any]) -> None:
        self.tc.log.append(kind, payload)


def outcome_of(close_event) -> str:
    """completed | dropped | error — an error on the close outranks a tidy reason."""
    if getattr(close_event, "error", None) is not None:
        return "error"
    reason = str(getattr(close_event.reason, "value", close_event.reason))
    return OUTCOMES.get(reason, "completed")


def turn_metrics(metrics) -> dict[str, float]:
    """The latencies we keep, rounded to milliseconds; an absent one is simply absent.

    `MetricsReport` is a total=False TypedDict, so which keys exist depends on
    the turn: a text-only session has no `tts_node_ttfb`, a greeting nobody was
    asked for has no `e2e_latency`. Asserting on the shape would be asserting
    on the modality.
    """
    if not metrics:
        return {}
    return {
        key: round(float(metrics[key]), 3)
        for key in TURN_METRICS
        if isinstance(metrics.get(key), (int, float))
    }
