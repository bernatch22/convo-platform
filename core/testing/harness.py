"""Bridge between LiveKit's in-process AgentSession and our tests / DeepEval.

`session.run()` is what the console uses; here it runs headless so a test can
assert on the exact events (messages, tool calls, handoffs) and DeepEval can
score the text. Nothing here touches audio or a LiveKit server.

Two ways in, one machine underneath. `run_conversation` plays a script that was
written before the call — the ms-2 and ms-3 goldens. `live_conversation` holds
the same session open and lets the caller decide the next line after hearing the
last one, which is what a simulated patient (ms-3 evals) does.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from livekit.agents import AgentSession
from livekit.agents.metrics import AgentSessionUsage, LLMModelUsage
from livekit.agents.voice import Agent
from livekit.agents.voice.run_result import ChatMessageAssert, RunResult

from core.context import TenantContext
from core.registry import load_registry
from core.session import build_session
from core.tools.executor import ToolExecutor, attach_local_tools

GREETING_WAIT_S = 6.0
TODAY = date(2026, 9, 1)  # a Tuesday: "el jueves" is always two days out in tests


def fake_context(
    tenant_id: str,
    project_id: str,
    channel: str = "chat",
    today: date = TODAY,
) -> TenantContext:
    """A TenantContext for tests: real tenant and project, synthetic ids, a frozen calendar.

    `today` is fixed so a test can name the date it expects ("el jueves" is
    2026-09-03) without the assertion rotting overnight; wired with the tenant's
    adapters and a local executor exactly as `core.router.resolve` wires one.
    """
    tenant = load_registry()[tenant_id]
    project = tenant.projects[project_id]
    tc = TenantContext(
        tenant=tenant,
        project=project,
        channel=channel,
        session_id=f"test-{uuid.uuid4().hex[:8]}",
        git_sha="test",
        project_version="git:test",
        today=today,
    )
    return attach_local_tools(tc)


@dataclass
class PlatformCall:
    """One tool the PLATFORM ran during a turn, and whether the customer's system took it.

    The other half of the story a `RunResult` tells. `book_appointment` is a
    tool the MODEL calls, and it calls it before the caller has agreed to
    anything — reading the hour back and waiting for a yes is what it does. The
    write that needs consent is `book_slot`, which the platform runs itself
    once `ConfirmTask` has minted a token, and no event in the run says when
    that happened. An eval that judges "nothing was booked before the yes" off
    the model's calls alone is judging the wrong event.
    """

    name: str
    args: dict[str, Any]
    ok: bool
    result: Any = None


@dataclass
class Exchange:
    """One turn of a conversation: what the caller said, what came back, what it ran."""

    input: str
    result: RunResult
    platform_calls: list[PlatformCall] = field(default_factory=list)


@dataclass
class Conversation:
    """What a headless run produced: the opening line, one exchange per input, the token bill."""

    greeting: str
    exchanges: list[Exchange] = field(default_factory=list)
    usage: AgentSessionUsage | None = None

    @property
    def results(self) -> list[RunResult]:
        """The per-turn run results, in order — what a golden asserts on."""
        return [exchange.result for exchange in self.exchanges]

    def reply(self, index: int) -> str:
        """The assistant text of the n-th turn."""
        return text_of(self.results[index])

    def cached_prompt_tokens(self) -> int:
        """Prompt tokens the LLM served from its cache — 0 means the prefix was never reused."""
        if self.usage is None:
            return 0
        return sum(
            model.input_cached_tokens
            for model in self.usage.model_usage
            if isinstance(model, LLMModelUsage)
        )


@dataclass
class LiveCall:
    """A session that is still on the line: say one thing, read the answer, decide the next."""

    session: AgentSession
    recorder: "RecordingExecutor"
    conversation: Conversation

    async def say(self, text: str) -> RunResult:
        """Say one line as the caller and record the whole turn it produced."""
        result = await self.session.run(user_input=text)
        self.conversation.exchanges.append(
            Exchange(input=text, result=result, platform_calls=self.recorder.take())
        )
        return result


class RecordingExecutor:
    """A `ToolExecutor` that also writes down every platform tool the current turn ran.

    A decorator, not a fork: it delegates to the real executor, so the guard,
    the timeouts and the spoken failure sentences all still apply and what it
    records is what actually happened. Only the harness installs it.
    """

    def __init__(self, inner: ToolExecutor) -> None:
        self.inner = inner
        self.calls: list[PlatformCall] = []

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        """Run the tool through the real executor, keeping the attempt either way."""
        try:
            result = await self.inner.call(name, args)
        except Exception:
            self.calls.append(PlatformCall(name=name, args=dict(args), ok=False))
            raise
        self.calls.append(PlatformCall(name=name, args=dict(args), ok=True, result=result))
        return result

    def take(self) -> list[PlatformCall]:
        """Everything run since the last take, and start counting the next turn."""
        calls, self.calls = self.calls, []
        return calls


@asynccontextmanager
async def live_conversation(
    tc: TenantContext, agent: Agent | None = None
) -> AsyncIterator[LiveCall]:
    """Open a headless call and hold it there until the caller hangs up.

    For anything that writes the next user line only after hearing the last
    one. Replaying the script from scratch on every turn would cost n(n+1)/2
    turns instead of n and — worse — re-generate the replies that line was
    answering, so the transcript scored afterwards is one nobody ever had.
    """
    recorder = _recording(tc)
    session: AgentSession[TenantContext] = build_session(tc)
    async with session:
        await session.start(agent or tc.project.entry_agent(tc))
        await _wait_for_greeting(session)
        recorder.take()  # anything the opening line ran belongs to no turn
        call = LiveCall(
            session=session,
            recorder=recorder,
            conversation=Conversation(greeting=greeting_of(session)),
        )
        try:
            yield call
        finally:
            # read before the context manager closes: leaving it resets the usage collector
            call.conversation.usage = session.usage


async def run_conversation(
    tc: TenantContext, inputs: list[str], agent: Agent | None = None
) -> Conversation:
    """Start a stage headless, capture its greeting, run each input as a turn.

    The greeting comes from `on_enter` before any user input, exactly as on a
    real call; goldens that judge the opening line read `Conversation.greeting`.

    `agent` defaults to the project's entry agent, which is what a real call
    starts with. A test passes a later stage when what it is pinning belongs to
    that stage and driving the conversation there through the model would only
    add turns, cost and variance to an assertion about something else.
    """
    async with live_conversation(tc, agent) as call:
        for text in inputs:
            await call.say(text)
        return call.conversation


async def run_turns(
    tc: TenantContext, inputs: list[str], agent: Agent | None = None
) -> list[RunResult]:
    """Convenience: only the per-input results of `run_conversation`."""
    return (await run_conversation(tc, inputs, agent)).results


def text_of(result: RunResult) -> str:
    """The assistant's spoken text for one turn (RunResult has no .text of its own)."""
    parts = [
        e.item.text_content or ""
        for e in result.events
        if e.type == "message" and e.item.role == "assistant"
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def final_message(result: RunResult) -> ChatMessageAssert:
    """The turn's LAST assistant message, ready to assert on or hand to a judge.

    One turn can hold several: Haiku often says "un momento, le consulto la
    agenda" before calling a tool and only answers once the result is back.
    Judging the first message would be judging the filler, so a golden about
    what the agent ANSWERS reads this one; a golden about the order of events
    (a tool call before the answer) still walks `result.expect` itself.
    """
    for index in reversed(range(len(result.events))):
        event = result.events[index]
        if event.type == "message" and event.item.role == "assistant":
            return result.expect[index].is_message(role="assistant")
    raise AssertionError("the turn produced no assistant message at all")


def greeting_of(session: AgentSession) -> str:
    """The first assistant message in the session history."""
    for item in session.history.items:
        if getattr(item, "role", None) == "assistant":
            return item.text_content or ""
    return ""


def _recording(tc: TenantContext) -> RecordingExecutor:
    """Wrap the context's executor once, and start the ledger empty."""
    if not isinstance(tc.tools, RecordingExecutor):
        tc.tools = RecordingExecutor(tc.tools)
    tc.tools.take()
    return tc.tools


async def _wait_for_greeting(session: AgentSession, timeout: float = GREETING_WAIT_S) -> None:
    """Poll until the entry agent's greeting lands in the history (or give up quietly)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if greeting_of(session):
            return
        await asyncio.sleep(0.2)
