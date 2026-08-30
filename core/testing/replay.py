"""Ring 3: a stored session read back as the same ConversationalTestCase ring 1 scores.

Rings 1 and 2 build a case from a conversation we just ran and still hold in
memory. Ring 3 has only the append-only log — a list of `Event`s written during
a call that ended hours ago, possibly on another machine — and has to rebuild
the case from that. The metrics do not change: `never_book_before_yes` and
`grounded_facts_dag` are the project's, and they read `turns` and
`tools_called` exactly as they do on a golden.

The turns are `turn.user` and `turn.agent` in seq order, and the tool events
between two agent turns hang from the **following** assistant turn: Haiku says
"un momento, le consulto la agenda", the tools run, and the answer is what they
produced.

**What ring 3 cannot see, and it is not a bug in this file.** The executor
records `tool.result` as a SHAPE (`list[3]`, `str[41]`), never the payload: a
log that kept what the agenda returned would keep the patient's hours, doctor
and phone next to their masked DNI, which is the one thing `pii_scope` exists
to prevent. So consent (`never_book_before_yes`) works in full — it reads tool
NAMES, and `book_slot` is in the log because the platform ran it — while
grounding (`grounded_facts_dag`) cannot ground a fact that came off the agenda:
the claim reaches the judge with evidence that could not contain it, and the
judge says no. That 0.0 means "not verifiable from the log", never "invented",
and `missing_tool_outputs` names the calls it applies to so a caller can say so.

The field that would close it — a `pii_scope`-filtered `summary` on
`tool.result` — is proposed and deliberately not built here: it changes
`ToolSpec` and the executor. `docs/evals.md` §3.6 and §8 carry the whole story.

Open source note: nothing below knows about clinics or about LiveKit. It reads
a `Store` and returns DeepEval objects, so any project whose log speaks these
kinds gets ring 3 for free.
"""

from collections.abc import Mapping

from deepeval.test_case import ConversationalTestCase, ToolCall, Turn

from core.state.events import Event
from core.state.store import Store
from core.testing.deepeval import tool_descriptions
from core.testing.harness import fake_context

TURN_KINDS = {"turn.user": "user", "turn.agent": "assistant"}
CALL_KINDS = ("tool.call", "tool.refused")
RESULT_KINDS = ("tool.result", "tool.error")

NO_PAYLOAD = (
    "the session log records the shape of a result, never its contents "
    "(PII), so what this call returned is not available here"
)
REFUSED = "refused before it ran ({reason}) — nothing was written"
FAILED = "the call failed ({key}) and nothing usable came back"
SCENARIO = "A real {channel} session of {tenant}/{project}, replayed from its append-only log."


def conversational_case_from(
    store: Store,
    session_id: str,
    descriptions: Mapping[str, str] | None = None,
) -> ConversationalTestCase:
    """One stored session as the multi-turn case a ConversationalDAGMetric reads.

    `descriptions` is the project's tool contracts by name (`descriptions_for`),
    so a judge shown a call also sees what that tool was for. No
    `expected_outcome`: a real call is not a golden, nobody wrote down what it
    was supposed to do, and inventing one here would be the eval marking its own
    homework.
    """
    row = store.session(session_id)
    if row is None:
        raise LookupError(f"no session {session_id!r} in this store")
    return ConversationalTestCase(
        turns=turns_from(store.events(session_id), descriptions),
        name=session_id,
        scenario=SCENARIO.format(channel=row.channel, tenant=row.tenant, project=row.project),
    )


def turns_from(
    events: list[Event],
    descriptions: Mapping[str, str] | None = None,
) -> list[Turn]:
    """The log's turns, in seq order, each assistant turn carrying what it ran.

    Pure and model-free: hand it a list of events and it hands back turns, which
    is how the conversion is tested without spending a cent.
    """
    turns: list[Turn] = []
    pending = _Calls(descriptions)
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


def descriptions_for(tenant_id: str, project_id: str) -> dict[str, str]:
    """Every tool of every stage of a project, described as the model reads it.

    A stored session has a tenant and a project on its row but no live context,
    so one is built offline exactly as the test harness builds one — the
    adapters are never called, only the stages' docstrings are read.
    """
    return tool_descriptions(fake_context(tenant_id, project_id))


def missing_tool_outputs(case: ConversationalTestCase) -> list[str]:
    """The tools whose result a grounding metric cannot see, once each, in order.

    Anything a caller states that came from one of these has no evidence behind
    it in a replayed case — not because the agent invented it, but because the
    log never stored it. A CLI or a report says this next to the score.
    """
    names: list[str] = []
    for turn in case.turns:
        for call in turn.tools_called or []:
            blind = call.output is None or NO_PAYLOAD in str(call.output)
            if blind and call.name not in names:
                names.append(call.name)
    return names


class _Calls:
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
        """Give the oldest unanswered call of that name its outcome; a stray result is dropped.

        Oldest first because the executor awaits one call at a time per chain,
        and there is no call id in the log to pair on — the name and the order
        are all a reader of the log has, so they are all this uses.
        """
        waiting = self.open.get(tool) or []
        if not waiting:
            return  # the call was on a previous turn, or the log starts mid-call
        self.calls[waiting.pop(0)].output = self._outcome(event)

    def _outcome(self, event: Event) -> str:
        if event.kind == "tool.error":
            return FAILED.format(key=event.payload.get("key", "unknown"))
        return f"{event.payload.get('shape', 'unknown')} — {NO_PAYLOAD}"

    def _refusal(self, event: Event) -> str | None:
        if event.kind != "tool.refused":
            return None
        return REFUSED.format(reason=event.payload.get("reason", "no reason recorded"))


def _attach_trailing(turns: list[Turn], calls: list[ToolCall] | None) -> None:
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
