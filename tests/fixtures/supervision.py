"""Fixtures and fakes shared by the supervision tests."""

import asyncio
import json
from typing import Any

import pytest
from livekit.agents.llm import ChatContext

from convo.agents import TenantAgent
from convo.supervision import monitor
from convo.supervision.control import (
    SupervisorControl,
)
from convo.testing import fake_context

SUP = "sup:berna"
CALLER = "clinica-norte:u1"


# ── the fakes: exactly the surface a supervisor's verb touches ────────────────


class FakeAgent:
    """An agent that only remembers the contexts it was handed."""

    def __init__(self, chat_ctx: ChatContext | None = None) -> None:
        self.chat_ctx = chat_ctx if chat_ctx is not None else ChatContext()
        self.updates: list[ChatContext] = []

    async def update_chat_ctx(self, chat_ctx: ChatContext) -> None:
        self.updates.append(chat_ctx)
        self.chat_ctx = chat_ctx


class FakeInput:
    def __init__(self) -> None:
        self.audio_enabled = True

    def set_audio_enabled(self, enabled: bool) -> None:
        self.audio_enabled = enabled


class FakeOptions:
    def __init__(self) -> None:
        self.interruption = {"resume_false_interruption": True}


class FakeSession:
    """The five things `SupervisorControl` reads off a session, and nothing more."""

    def __init__(self, agent: FakeAgent, speaking: bool = False, running: bool = True) -> None:
        self.current_agent = agent
        self.agent_state = "speaking" if speaking else "listening"
        self.current_speech = object() if speaking else None
        self.input = FakeInput()
        self.options = FakeOptions()
        self.running = running
        self.interrupts = 0
        self.replies: list[dict[str, Any]] = []

    def interrupt(self, *, force: bool = False):
        if not self.running:
            raise RuntimeError("AgentSession isn't running")
        self.interrupts += 1
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        done.set_result(None)
        return done

    def generate_reply(self, **kwargs: Any) -> None:
        self.replies.append(kwargs)


class Invocation:
    """`RpcInvocationData` as the SFU builds it: the identity is off the JWT, not the payload."""

    def __init__(self, caller_identity: str, payload: dict[str, Any]) -> None:
        self.caller_identity = caller_identity
        self.payload = json.dumps(payload)


class Packet:
    """A data packet; `participant=None` is the SFU's word for "a server SDK sent this"."""

    def __init__(self, body: dict[str, Any], participant: Any = None) -> None:
        self.data = json.dumps(body).encode("utf-8")
        self.topic = monitor.TOPIC
        self.participant = participant


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


@pytest.fixture
def agent() -> FakeAgent:
    return FakeAgent()


@pytest.fixture
def session(agent: FakeAgent) -> FakeSession:
    return FakeSession(agent)


@pytest.fixture
def control(tc, session: FakeSession) -> SupervisorControl:
    return SupervisorControl(tc, session)


class _Stage(TenantAgent):
    """A stage running outside any activity: `session` is the fake, as it is in a job."""

    def __init__(self, tc, session: FakeSession) -> None:
        super().__init__(tc, instructions="stage")
        self._live = session

    @property
    def session(self) -> Any:
        return self._live


class _Room:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.methods: dict[str, Any] = {}
        self.local_participant = self

    def on(self, event: str, handler: Any) -> None:
        self.handlers[event] = handler

    def register_rpc_method(self, name: str, handler: Any) -> None:
        self.methods[name] = handler


def _said(text: str):
    """A user turn as the framework hands it to `on_user_turn_completed`."""
    from livekit.agents.llm import ChatMessage

    return ChatMessage(role="user", content=[text])
