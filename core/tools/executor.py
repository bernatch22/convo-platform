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

from core.state.log import record
from core.tools import guard
from core.tools.contract import ToolSpec
from core.tools.messages import FAILURE, NO_ADAPTER, TIMEOUT, UNKNOWN_TOOL, sentence

if TYPE_CHECKING:  # avoid an import cycle: core.context declares the executor it carries
    from core.adapters.base import Adapter
    from core.context import TenantContext

log = logging.getLogger("platform.tools")

# The keys of `tc.customer` that identify a person. A project fills that dict
# from its own CRM, so this is a convention, not a schema — an unknown key is
# simply not learned, and the tool that carries it still masks it by name.
CUSTOMER_PII_KEYS = ("patient", "name", "phone")


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
        self._learn_pii(spec, args)
        safe_args = guard.mask(spec, args, known=self.tc.pii_values)
        try:
            guard.check(spec, args, self.tc)
        except guard.ToolRefused as refusal:
            self._record("tool.refused", spec, args=safe_args, reason=refusal.reason)
            raise
        adapter = self._adapter(spec)
        log.info("tool.call %s %s args=%s", self.tc.label(), spec.name, safe_args)
        self._record("tool.call", spec, args=safe_args)
        result = await self._execute(spec, adapter, args, safe_args)
        guard.consume(spec, self.tc)
        self._record("tool.result", spec, shape=_shape(result))
        log.info("tool.result %s %s ok", self.tc.label(), spec.name)
        return result

    def _learn_pii(self, spec: ToolSpec, args: dict[str, Any]) -> None:
        """Remember this call's PII values BEFORE masking, so its own log line is masked too.

        Order is the whole point. `send_sms` carries the patient's name inside
        `text`, and the only reason we know that string is a name is that some
        argument, somewhere, declared it. Learning after masking would leak the
        first occurrence of every value — which is the one that matters.
        """
        guard.learn(self.tc.pii_values, guard.pii_values(spec, args))
        guard.learn(self.tc.pii_values, _identity_of(self.tc.customer))

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
            self._record("tool.error", spec, key=TIMEOUT)
            raise ToolError(self._says(TIMEOUT)) from None
        except Exception:
            log.exception("tool.error %s %s failed args=%s", self.tc.label(), spec.name, safe_args)
            self._record("tool.error", spec, key=FAILURE)
            raise ToolError(self._says(FAILURE)) from None

    def _record(self, kind: str, spec: ToolSpec, **payload: Any) -> None:
        """One line in the session log, when the context carries one; payloads never enter it.

        `record` scrubs known PII values from whatever this hands it, so a
        refusal reason or a timeout note cannot leak a name the arguments
        already had masked.
        """
        record(self.tc, kind, {"tool": spec.name, "side_effect": str(spec.side_effect), **payload})

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


def _identity_of(customer: dict[str, Any] | None) -> list[Any]:
    """Who the caller is, by the conventional keys a project puts on `tc.customer`.

    A session knows the patient's name from the moment Identify found them,
    before any tool has carried it as an argument. Naming the keys here — and
    not reading the whole dict — keeps an appointment id or a doctor out of the
    mask, which would blank half of every log line for nothing.
    """
    return [(customer or {}).get(key) for key in CUSTOMER_PII_KEYS]


def _shape(result: Any) -> str:
    """What a result looked like, never what it said: `list[3]`, `dict[2]`, `str[41]`."""
    if isinstance(result, (list, dict, str)):
        return f"{type(result).__name__}[{len(result)}]"
    return type(result).__name__
