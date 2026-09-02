"""Saga: several tool calls that must all happen, or be undone in reverse.

Rebooking an appointment is three writes on three systems — cancel the old
slot, book the new one, send the SMS — and the second can fail after the first
succeeded. A saga runs the steps in order through the executor (so every step
is catalogued, guarded, timed and logged like any other call) and, when one
fails, runs the `compensation` tool declared on the ToolSpec of each completed
step, last first. The original failure is what the caller hears; a compensation
that fails too is logged, never allowed to hide it.

Compensations run through the same executor, so they need their own ToolSpec
and adapter capability. Declare them `write`, not `irreversible`: the platform
is undoing on the caller's behalf, and asking for a second yes to put things
back the way they were is not a conversation anyone wants.

Open source note: framework-agnostic; the contract is `tc.tools.call` and, for
the audit trail, `tc.log` — which may be absent, and then the saga is silent.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from convo.state.log import record

log = logging.getLogger("platform.saga")

UndoArgs = Callable[[Any], dict[str, Any]]


@dataclass
class Step:
    """One tool call of the saga and how to derive its undo arguments from its result."""

    name: str
    args: dict[str, Any]
    undo_args: UndoArgs | None = None
    result: Any = None
    done: bool = False


class SagaFailed(Exception):
    """A step failed; `compensated` names the completed steps that were undone, last first."""

    def __init__(self, step: str, cause: Exception, compensated: list[str]) -> None:
        super().__init__(f"saga failed at {step}: {cause}")
        self.step = step
        self.cause = cause
        self.compensated = compensated


@dataclass
class Saga:
    """Build with `.step(...)` calls, then `await run()`: results in order, or SagaFailed."""

    tc: Any
    steps: list[Step] = field(default_factory=list)

    def step(self, name: str, args: dict[str, Any], undo_args: UndoArgs | None = None) -> "Saga":
        """Append a tool call; `undo_args(result)` builds the compensation's arguments.

        Without it the compensation receives the step's own arguments, which is
        right when undoing needs nothing the call produced (re-book what we
        cancelled). Chainable: `Saga(tc).step(...).step(...)`.
        """
        self.steps.append(Step(name=name, args=args, undo_args=undo_args))
        return self

    async def run(self) -> list[Any]:
        """Execute every step in order; on failure compensate the completed ones and raise."""
        for step in self.steps:
            try:
                step.result = await self.tc.tools.call(step.name, step.args)
                step.done = True
            except Exception as cause:
                log.warning("saga.fail %s step=%s cause=%s", self.tc.label(), step.name, cause)
                record(self.tc, "saga.fail", {"step": step.name, "cause": str(cause)})
                compensated = await self._compensate()
                record(
                    self.tc,
                    "saga.rolled_back",
                    {
                        "failed_at": step.name,
                        "compensated": compensated,
                        "steps": [s.name for s in self.steps],
                    },
                )
                raise SagaFailed(step.name, cause, compensated) from cause
        return [step.result for step in self.steps]

    async def _compensate(self) -> list[str]:
        compensated: list[str] = []
        for step in reversed([s for s in self.steps if s.done]):
            spec = self.tc.project.tools.get(step.name)
            undo = spec.compensation if spec else None
            if not undo:
                log.warning("saga.no_undo %s step=%s", self.tc.label(), step.name)
                record(self.tc, "saga.no_undo", {"step": step.name})
                continue
            args = step.undo_args(step.result) if step.undo_args else step.args
            try:
                await self.tc.tools.call(undo, args)
                compensated.append(step.name)
                record(self.tc, "saga.compensated", {"step": step.name, "undo": undo})
            except Exception:
                log.exception(
                    "saga.undo_failed %s step=%s undo=%s", self.tc.label(), step.name, undo
                )
                record(self.tc, "saga.undo_failed", {"step": step.name, "undo": undo})
        return compensated
