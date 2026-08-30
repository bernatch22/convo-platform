"""LocalExecutor: run one tool call in this process — looked up, guarded, timed and logged.

The ToolError contract
----------------------
`livekit.agents.llm.ToolError` is the one exception a tool may raise that the
model gets to read: its message is handed back as the tool's output, so it must
be a sentence a caller could hear in the project's language — never a stack
trace, never an internal identifier, never the name of a system. Every other
failure (an undeclared tool, a missing adapter, an adapter blowing up, a
timeout) is translated here into exactly that, and the real cause goes to the
log instead. Which sentence is spoken comes from `core.tools.messages`, so a
project chooses its own register.

This module is the only file in `core/tools` that imports livekit: `contract`,
`guard`, `catalog` and `messages` stay framework-agnostic, so porting the
platform to another agent runtime means rewriting this file alone.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Protocol

from livekit.agents.llm import ToolError

from core.tools import guard
from core.tools.contract import ToolSpec
from core.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL, sentence

if TYPE_CHECKING:  # avoid an import cycle: core.context declares the executor it carries
    from core.adapters.base import Adapter
    from core.context import TenantContext

log = logging.getLogger("platform.tools")


class ToolExecutor(Protocol):
    """What a stage calls to run a tool: one coroutine, a name and arguments in, a result out."""

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        """Run the tool: returns its result, raises ToolError (spoken) or ToolRefused (vetoed)."""
        ...


class LocalExecutor:
    """Runs tools in the agent's own process, against the adapters of one TenantContext.

    Remote execution (the customer's own code, ms-12) is a second implementation
    of `ToolExecutor`; nothing above this line changes when it arrives.
    """

    def __init__(self, tc: "TenantContext") -> None:
        self.tc = tc

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        """Run one declared tool: catalog, guard, adapter, timeout, log — in that order."""
        spec = self._spec(name)
        guard.check(spec, args, self.tc)
        adapter = self._adapter(spec)
        safe_args = guard.mask(spec, args)
        log.info("tool.call %s %s args=%s", self.tc.label(), spec.name, safe_args)
        result = await self._execute(spec, adapter, args, safe_args)
        log.info("tool.result %s %s ok", self.tc.label(), spec.name)
        return result

    def _spec(self, name: str) -> ToolSpec:
        spec = self.tc.project.tools.get(name)
        if spec is None:
            log.warning(
                "tool.error %s %s undeclared; catalog=%s",
                self.tc.label(),
                name,
                self.tc.project.tools.names(),
            )
            raise ToolError(self._says(UNKNOWN_TOOL))
        return spec

    def _adapter(self, spec: ToolSpec) -> "Adapter":
        for adapter in self.tc.adapters.values():
            if adapter.supports(spec.name):
                return adapter
        log.warning(
            "tool.error %s %s has no adapter; adapters=%s",
            self.tc.label(),
            spec.name,
            sorted(self.tc.adapters),
        )
        raise ToolError(self._says(NO_ADAPTER))

    async def _execute(
        self,
        spec: ToolSpec,
        adapter: "Adapter",
        args: dict[str, Any],
        safe_args: dict[str, Any],
    ) -> Any:
        try:
            async with asyncio.timeout(spec.timeout_s):
                return await adapter.execute(spec.name, args)
        except ToolError:
            raise  # the adapter already wrote a sentence for the caller
        except TimeoutError:
            log.warning(
                "tool.error %s %s timeout after %ss args=%s",
                self.tc.label(),
                spec.name,
                spec.timeout_s,
                safe_args,
            )
            raise ToolError(self._says(TIMEOUT)) from None
        except Exception:
            log.exception("tool.error %s %s failed args=%s", self.tc.label(), spec.name, safe_args)
            raise ToolError(self._says(FAILURE)) from None

    def _says(self, key: str) -> str:
        return sentence(self.tc.project.messages, key)


def attach_local_tools(tc: "TenantContext") -> "TenantContext":
    """Give a freshly built context its tenant's adapters and a local executor over them.

    Two steps that only make sense together and only after the context exists
    (the executor holds it), so every builder of a TenantContext — the router in
    production, the harness in tests — ends with this one line.
    """
    tc.adapters = tc.tenant.build_adapters()
    tc.tools = LocalExecutor(tc)
    return tc
