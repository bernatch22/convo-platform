"""Bridge between LiveKit's in-process AgentSession and our tests / DeepEval.

Decisions: docs/decisions/convo.testing.harness.md
"""

import asyncio
import dataclasses
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from livekit.agents import AgentSession
from livekit.agents.metrics import AgentSessionUsage, LLMModelUsage
from livekit.agents.utils import http_context
from livekit.agents.voice import Agent
from livekit.agents.voice.run_result import ChatMessageAssert, RunResult

from convo.domain.context import TenantContext
from convo.providers import llm
from convo.session.build import build_session
from convo.session.registry import load_registry
from convo.state.attach import attach_log
from convo.state.log import record as record_event
from convo.state.store import MemoryStore
from convo.testing.callers.speaker import open_recording
from convo.tools.executor import ToolExecutor, attach_local_tools

GREETING_WAIT_S = 6.0
TODAY = date(2026, 9, 1)  # a Tuesday: "el jueves" is always two days out in tests

# The model the whole run measures, for a suite nobody wants to edit per model:
# `CONVO_EVAL_MODEL=gpt-5.4-mini deepeval test run tests/evals` moves every golden
# of every project onto the other model, and unset means the project's own.
MODEL_ENV = "CONVO_EVAL_MODEL"


def model_under_test(explicit: str | None = None) -> str | None:
    """Which LLM this run measures: the argument, else $CONVO_EVAL_MODEL, else the project's."""
    wanted = explicit or os.getenv(MODEL_ENV) or None
    if wanted is None:
        return None
    if wanted not in llm.ALLOWED_MODELS:
        raise ValueError(
            f"{wanted!r} is not a model the platform runs: {', '.join(llm.ALLOWED_MODELS)}"
        )
    return wanted


def fake_context(
    tenant_id: str,
    project_id: str,
    channel: str = "chat",
    today: date = TODAY,
    llm_model: str | None = None,
) -> TenantContext:
    """A TenantContext for tests: real tenant and project, synthetic ids, a frozen calendar."""
    tenant = load_registry()[tenant_id]
    project = tenant.projects[project_id]
    model = model_under_test(llm_model)
    if model is not None:
        project = dataclasses.replace(project, llm_model=model)
    tc = TenantContext(
        tenant=tenant,
        project=project,
        channel=channel,
        session_id=f"test-{uuid.uuid4().hex[:8]}",
        git_sha="test",
        project_version="git:test",
        today=today,
    )
    return attach_log(attach_local_tools(tc), MemoryStore())


@dataclass
class PlatformCall:
    """One tool the PLATFORM ran during a turn, and whether the customer's system took it."""

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

    def lines_said(self) -> list[str]:
        """Everything the agent has said so far, greeting included, in order."""
        return [
            item.text_content or ""
            for item in self.session.history.items
            if getattr(item, "role", None) == "assistant" and (item.text_content or "").strip()
        ]

    async def next_line(self, after: int, timeout: float = 25.0) -> str:
        """Wait for a line the agent speaks on its OWN — nobody said anything to it."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if len(self.lines_said()) > after:
                await asyncio.sleep(1.0)  # let the rest of the turn land
                return " ".join(self.lines_said()[after:])
            await asyncio.sleep(0.25)
        return ""


class RecordingExecutor:
    """A `ToolExecutor` that also writes down every platform tool the current turn ran."""

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
    tc: TenantContext, agent: Agent | None = None, record: str | Path | None = None
) -> AsyncIterator[LiveCall]:
    """Open a headless call and hold it there until the caller hangs up."""
    recorder = _recording(tc)
    session: AgentSession[TenantContext] = build_session(tc)
    async with AsyncExitStack() as stack:
        audio = None
        if record:
            # the TTS plugin borrows the worker's aiohttp session, and outside a
            # worker there is none to borrow: this is that session, for this call
            await stack.enter_async_context(http_context.open())
            audio = await open_recording(session, record)
            record_event(tc, "audio.start", {"path": str(audio.path)})
        await stack.enter_async_context(session)
        await session.start(agent or tc.project.entry_agent(tc))
        if audio is not None:
            audio.adopt()
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
            if audio is not None:
                await audio.aclose()


async def run_conversation(
    tc: TenantContext, inputs: list[str], agent: Agent | None = None
) -> Conversation:
    """Start a stage headless, capture its greeting, run each input as a turn."""
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
    """The turn's LAST assistant message, ready to assert on or hand to a judge."""
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
