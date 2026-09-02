"""A caller nobody scripted: DeepEval's ConversationSimulator against a real headless stage.

Decisions: docs/decisions/convo.testing.callers.simulator.md
"""

import os
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack

from deepeval.dataset import ConversationalGolden
from deepeval.models import AnthropicModel
from deepeval.simulator import ConversationSimulator
from deepeval.simulator.controller import end, proceed
from deepeval.simulator.controller.types import Decision
from deepeval.test_case import ConversationalTestCase, Turn
from deepeval.utils import get_or_create_event_loop
from livekit.agents.voice import Agent

from convo.domain.context import TenantContext
from convo.testing.harness import LiveCall, live_conversation, text_of
from convo.testing.metrics.deepeval import (
    conversational_test_case_for,
    tool_descriptions,
    turn_tool_calls,
)

SIMULATOR_MODEL = os.getenv("DEEPEVAL_JUDGE_MODEL", "claude-haiku-4-5")
DEFAULT_MAX_USER_TURNS = 6
ContextFactory = Callable[[ConversationalGolden], TenantContext]
EntryStage = Callable[[TenantContext], Agent]
StopRule = Callable[[Turn | None], Decision]


def settled_when(endings: Mapping[str, str]) -> StopRule:
    """End the call the moment one of these tools runs — no judge, just tool names."""

    def stop(last_assistant_turn: Turn | None) -> Decision:
        if last_assistant_turn is None:
            return proceed()
        called = {tool.name for tool in last_assistant_turn.tools_called or []}
        for name, why in endings.items():
            if name in called:
                return end(why)
        return proceed()

    return stop


class SimulatedCaller:
    """One project's agent, as one live call per simulated conversation."""

    def __init__(
        self,
        goldens: list[ConversationalGolden],
        tc_factory: ContextFactory,
        entry_stage: EntryStage,
        *,
        stop_when: StopRule,
        max_user_turns: int = DEFAULT_MAX_USER_TURNS,
    ) -> None:
        self.goldens = list(goldens)
        self._tc_factory = tc_factory
        self._entry_stage = entry_stage
        self._stop_when = stop_when
        self._max_user_turns = max_user_turns
        self._sessions = AsyncExitStack()
        self._calls: dict[str, LiveCall] = {}
        self._order: list[str] = []
        self._descriptions: dict[str, str] = {}

    def simulate(self) -> list[ConversationalTestCase]:
        """Run every golden once and return the conversations as multi-turn cases, in order."""
        simulator = ConversationSimulator(
            model_callback=self.answer,
            simulator_model=AnthropicModel(model=SIMULATOR_MODEL),
            stopping_controller=self._stop_when,
            language="Spanish",
            max_concurrent=1,
        )
        loop = get_or_create_event_loop()
        try:
            simulator.simulate(self.goldens, max_user_simulations=self._max_user_turns)
        finally:
            loop.run_until_complete(self.hang_up())
        return self.cases()

    async def answer(self, input: str, thread_id: str) -> Turn:
        """One line from the caller in, the stage's whole answer out, tools and all."""
        call = self._calls.get(thread_id) or await self._open(thread_id)
        result = await call.say(input)
        return Turn(
            role="assistant",
            content=text_of(result),
            tools_called=turn_tool_calls(call.conversation.exchanges[-1]),
        )

    async def hang_up(self) -> None:
        """Close every session that is still open; conversations stay readable afterwards."""
        await self._sessions.aclose()

    def cases(self) -> list[ConversationalTestCase]:
        """Each conversation as a multi-turn case, carrying the golden that drove it."""
        if len(self._order) != len(self.goldens):
            raise AssertionError(
                f"{len(self._order)} conversations ran for {len(self.goldens)} goldens: "
                "a simulated call produced no user turn at all"
            )
        return [
            conversational_test_case_for(
                self._calls[thread].conversation,
                self._descriptions,
                scenario=golden.scenario,
                expected_outcome=golden.expected_outcome,
                name=golden.name,
            )
            for thread, golden in zip(self._order, self.goldens, strict=True)
        ]

    async def _open(self, thread_id: str) -> LiveCall:
        """Start a call for a conversation the simulator has just begun."""
        tc = self._tc_factory(self.goldens[len(self._order)])
        self._descriptions = self._descriptions or tool_descriptions(tc)
        live = live_conversation(tc, self._entry_stage(tc))
        self._calls[thread_id] = await self._sessions.enter_async_context(live)
        self._order.append(thread_id)
        return self._calls[thread_id]
