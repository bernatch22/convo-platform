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

from core import confirm
from core.context import Project, Tenant, TenantContext
from core.tools.catalog import ToolCatalog, platform_specs
from core.tools.contract import SideEffect, ToolSpec
from core.tools.executor import SUMMARY_CHARS, LocalExecutor
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
        self.result: Any = None  # set it to answer something other than the two default slots

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
        if self.result is not None:
            return self.result
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

    confirm.mint(tc, "cancel_appointment", {"phone": "600123456"})
    await tc.tools.call("cancel_appointment", {"phone": "600123456"})

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

    confirm.mint(tc, "cancel_appointment", {"phone": "600123456"})
    with caplog.at_level(logging.INFO, logger="platform.tools"):
        await tc.tools.call("cancel_appointment", {"phone": "600123456"})

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
    args = {"phone": "600123456"}
    confirm.mint(tc, "cancel_appointment", args)  # irreversible: the guard needs a real yes

    await tc.tools.call("cancel_appointment", args)

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


# ── result summaries: the one line of a payload the log may keep (ms-7) ──────


def summarising(renderer) -> ToolCatalog:
    """The same catalog with `find_availability` declaring `renderer` as its summary."""
    spec = ToolSpec(
        name="find_availability",
        side_effect=SideEffect.READ,
        timeout_s=5.0,
        result_summary=renderer,
    )
    return CATALOG.merge(ToolCatalog.of(spec))


def result_payload(tc) -> dict:
    return next(payload for kind, payload in logged(tc) if kind == "tool.result")


async def test_a_tool_that_declares_no_summary_logs_exactly_what_it_always_logged() -> None:
    """The opt-in half of the contract: an untouched project's log does not change."""
    tc = attached(context(FakeAdapter()))

    await tc.tools.call("find_availability", {"date": "2026-09-01"})

    assert result_payload(tc) == {
        "tool": "find_availability",
        "side_effect": "read",
        "shape": "dict[2]",
    }


async def test_a_declared_summary_is_written_next_to_the_shape_never_instead_of_it() -> None:
    tc = attached(context(FakeAdapter(), summarising(lambda r: f"free: {', '.join(r['slots'])}")))

    await tc.tools.call("find_availability", {"date": "2026-09-01"})

    assert result_payload(tc)["summary"] == "free: 10:00, 12:30"
    assert result_payload(tc)["shape"] == "dict[2]", "the shape is what a reader counts by"


async def test_a_renderer_that_explodes_costs_the_log_a_line_and_the_caller_nothing() -> None:
    """A bug in a log line must never fail a tool call the adapter already answered."""

    def broken(result: Any) -> str:
        raise KeyError("doctor")

    tc = attached(context(FakeAdapter(), summarising(broken)))

    result = await tc.tools.call("find_availability", {"date": "2026-09-01"})

    assert result == {"slots": ["10:00", "12:30"], "date": "2026-09-01"}
    assert "summary" not in result_payload(tc)


async def test_a_summary_longer_than_a_log_line_is_capped_and_says_so() -> None:
    tc = attached(context(FakeAdapter(), summarising(lambda r: "hueco " * 200)))

    await tc.tools.call("find_availability", {"date": "2026-09-01"})

    summary = result_payload(tc)["summary"]
    assert len(summary) == SUMMARY_CHARS and summary.endswith("…")


async def test_an_empty_summary_leaves_no_key_rather_than_an_empty_one() -> None:
    tc = attached(context(FakeAdapter(), summarising(lambda r: "")))

    await tc.tools.call("find_availability", {"date": "2026-09-01"})

    assert "summary" not in result_payload(tc)


async def test_a_name_the_arguments_never_carried_is_masked_because_the_result_carried_it() -> None:
    """`find_patient` is asked for a phone and answers with a person: the mask learns it here."""
    adapter = FakeAdapter()
    adapter.result = {"name": "Ana García Ruiz", "when": "2026-09-03T10:00"}
    tc = attached(context(adapter, summarising(lambda r: f"found {r['name']} for {r['when']}")))

    await tc.tools.call("find_availability", {"date": "2026-09-01"})

    assert result_payload(tc)["summary"] == "found An************* for 2026-09-03T10:00"


def attached(tc):
    """The same context with an in-memory log, for the assertions that read one."""
    from core.state.attach import attach_log
    from core.state.store import MemoryStore

    return attach_log(tc, MemoryStore())
