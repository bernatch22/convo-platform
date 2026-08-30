"""The platform side of a tool call: catalog lookup, guard, LocalExecutor.

No LLM and no network: one fake adapter stands in for a tenant's real systems,
so every path (result, refusal, failure, timeout, masking) is asserted in
milliseconds.
"""

import asyncio
import logging
from typing import Any

import pytest
from livekit.agents.llm import ToolError

from core.context import Project, Tenant, TenantContext
from core.tools.catalog import ToolCatalog, platform_specs
from core.tools.contract import SideEffect, ToolSpec
from core.tools.executor import LocalExecutor
from core.tools.guard import ToolRefused, mask
from core.tools.messages import DEFAULTS, FAILURE, TIMEOUT, UNKNOWN_TOOL

pytestmark = pytest.mark.unit

FIND_AVAILABILITY = ToolSpec(name="find_availability", side_effect=SideEffect.READ, timeout_s=5.0)
CANCEL_APPOINTMENT = ToolSpec(
    name="cancel_appointment",
    side_effect=SideEffect.IRREVERSIBLE,
    pii_scope=frozenset({"phone"}),
    timeout_s=5.0,
)
SLOW_LOOKUP = ToolSpec(name="slow_lookup", side_effect=SideEffect.READ, timeout_s=0.02)
BROKEN_LOOKUP = ToolSpec(name="broken_lookup", side_effect=SideEffect.READ, timeout_s=5.0)

CATALOG = ToolCatalog.of(FIND_AVAILABILITY, CANCEL_APPOINTMENT, SLOW_LOOKUP, BROKEN_LOOKUP)


class FakeAdapter:
    """An agenda that answers instantly, hangs, or explodes — whatever the test needs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> list[str]:
        return ["find_availability", "cancel_appointment", "slow_lookup", "broken_lookup"]

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities()

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        self.calls.append((capability, args))
        if capability == "slow_lookup":
            await asyncio.sleep(1)
        if capability == "broken_lookup":
            raise RuntimeError("agenda-db: connection refused at 10.0.0.7:5432")
        return {"slots": ["10:00", "12:30"], "date": args.get("date")}


def context(
    adapter: FakeAdapter,
    catalog: ToolCatalog = CATALOG,
    messages: dict[str, str] | None = None,
) -> TenantContext:
    """A TenantContext wired to the fake adapter and a LocalExecutor, with no registry."""
    tc = TenantContext(
        tenant=Tenant(id="clinica-norte", name="Clínica Norte"),
        project=Project(
            id="reagendamiento",
            name="Reagendamiento",
            tools=catalog,
            messages=messages or {},
        ),
        channel="chat",
        session_id="test",
        git_sha="test",
        project_version="git:test",
        adapters={"agenda": adapter},
    )
    tc.tools = LocalExecutor(tc)
    return tc


async def test_a_read_tool_runs_through_the_adapter_and_returns_its_result() -> None:
    adapter = FakeAdapter()
    tc = context(adapter)

    result = await tc.tools.call("find_availability", {"date": "2026-09-01"})

    assert result == {"slots": ["10:00", "12:30"], "date": "2026-09-01"}
    assert adapter.calls == [("find_availability", {"date": "2026-09-01"})]


async def test_a_tool_the_project_never_declared_reaches_the_llm_as_a_sentence() -> None:
    tc = context(FakeAdapter())

    with pytest.raises(ToolError) as refusal:
        await tc.tools.call("delete_patient", {"id": "42"})

    assert str(refusal.value) == DEFAULTS[UNKNOWN_TOOL]


async def test_an_irreversible_tool_without_a_confirmation_token_is_refused() -> None:
    adapter = FakeAdapter()
    tc = context(adapter)

    with pytest.raises(ToolRefused) as refusal:
        await tc.tools.call("cancel_appointment", {"phone": "600123456"})

    assert "cancel_appointment" in refusal.value.reason
    assert adapter.calls == [], "a refused tool must never reach the adapter"


async def test_an_irreversible_tool_with_a_confirmation_token_passes_the_guard() -> None:
    adapter = FakeAdapter()
    tc = context(adapter)

    await tc.tools.call(
        "cancel_appointment", {"phone": "600123456", "confirmation_token": "ct-abc123"}
    )

    assert adapter.calls[0][0] == "cancel_appointment"


async def test_an_adapter_that_explodes_never_leaks_its_stack_trace_to_the_llm() -> None:
    tc = context(FakeAdapter())

    with pytest.raises(ToolError) as failure:
        await tc.tools.call("broken_lookup", {"date": "2026-09-01"})

    assert str(failure.value) == DEFAULTS[FAILURE]
    assert "10.0.0.7" not in str(failure.value)
    assert "RuntimeError" not in str(failure.value)


async def test_an_adapter_that_hangs_is_cut_off_at_the_declared_timeout() -> None:
    tc = context(FakeAdapter())

    with pytest.raises(ToolError) as failure:
        await tc.tools.call("slow_lookup", {"date": "2026-09-01"})

    assert str(failure.value) == DEFAULTS[TIMEOUT]


async def test_pii_arguments_are_masked_before_they_reach_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tc = context(FakeAdapter())

    with caplog.at_level(logging.INFO, logger="platform.tools"):
        await tc.tools.call(
            "cancel_appointment", {"phone": "600123456", "confirmation_token": "ct-abc123"}
        )

    assert "60*******" in caplog.text
    assert "600123456" not in caplog.text


def test_mask_keeps_two_characters_and_leaves_non_pii_arguments_alone() -> None:
    masked = mask(CANCEL_APPOINTMENT, {"phone": "600123456", "date": "2026-09-01"})

    assert masked == {"phone": "60*******", "date": "2026-09-01"}


def test_the_platform_catalog_declares_find_availability_as_a_read_with_a_five_second_timeout() -> (
    None
):
    spec = platform_specs().get("find_availability")

    assert spec is not None
    assert spec.side_effect is SideEffect.READ
    assert spec.timeout_s == 5.0
    assert spec.needs_confirmation() is False


async def test_a_project_speaks_its_own_register_when_a_tool_fails() -> None:
    usted = "No he podido consultar la agenda. ¿Quiere que lo intente de nuevo?"
    tc = context(FakeAdapter(), messages={FAILURE: usted})

    with pytest.raises(ToolError) as failure:
        await tc.tools.call("broken_lookup", {"date": "2026-09-01"})

    assert str(failure.value) == usted
    assert str(failure.value) != DEFAULTS[FAILURE]


# --- the session log --------------------------------------------------------


def logged(tc) -> list[tuple[str, dict]]:
    return [(e.kind, e.payload) for e in tc.log.events()]


async def test_a_call_leaves_call_and_result_events_with_pii_masked() -> None:
    from core.state.attach import attach_log
    from core.state.store import MemoryStore

    tc = attach_log(context(FakeAdapter()), MemoryStore())

    await tc.tools.call(
        "cancel_appointment", {"phone": "600123456", "confirmation_token": "ct-abc123"}
    )

    kinds = [k for k, _ in logged(tc)]
    assert kinds == ["session.start", "tool.call", "tool.result"]
    call = logged(tc)[1][1]
    assert call["args"]["phone"] == "60*******" and call["side_effect"] == "irreversible"
    assert logged(tc)[2][1]["shape"] == "dict[2]"


async def test_a_refusal_and_a_failure_are_logged_without_payloads() -> None:
    from core.state.attach import attach_log
    from core.state.store import MemoryStore

    tc = attach_log(context(FakeAdapter()), MemoryStore())

    with pytest.raises(ToolRefused):
        await tc.tools.call("cancel_appointment", {"phone": "600123456"})
    with pytest.raises(ToolError):
        await tc.tools.call("broken_lookup", {"date": "2026-09-01"})

    kinds = [k for k, _ in logged(tc)]
    assert kinds == ["session.start", "tool.refused", "tool.call", "tool.error"]
    assert "10.0.0.7" not in str(logged(tc))
    assert logged(tc)[3][1]["key"] == FAILURE
