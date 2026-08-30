"""Saga: cancel → book → sms, and what happens to the cancel when the book fails."""

from typing import Any

import pytest

from core import confirm
from core.context import Project, Tenant, TenantContext
from core.tools.catalog import ToolCatalog
from core.tools.contract import SideEffect, ToolSpec
from core.tools.executor import LocalExecutor
from core.tools.saga import Saga, SagaFailed

pytestmark = pytest.mark.unit

CANCEL = ToolSpec(name="cancel_slot", side_effect=SideEffect.WRITE, compensation="rebook_slot")
REBOOK = ToolSpec(name="rebook_slot", side_effect=SideEffect.WRITE)
BOOK = ToolSpec(name="book_slot", side_effect=SideEffect.IRREVERSIBLE, compensation="cancel_slot")
SMS = ToolSpec(name="send_sms", side_effect=SideEffect.WRITE)
CATALOG = ToolCatalog.of(CANCEL, REBOOK, BOOK, SMS)


class Agenda:
    """Records every capability it runs; `failing` names the one that blows up."""

    def __init__(self, failing: str | None = None) -> None:
        self.failing = failing
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def capabilities(self) -> list[str]:
        return CATALOG.names()

    def supports(self, capability: str) -> bool:
        return True

    async def execute(self, capability: str, args: dict[str, Any]) -> Any:
        self.calls.append((capability, args))
        if capability == self.failing:
            raise RuntimeError("agenda down")
        return {"ok": True, "id": f"{capability}-1"}


def context(agenda: Agenda) -> TenantContext:
    tc = TenantContext(
        tenant=Tenant(id="t", name="T"),
        project=Project(id="p", name="P", tools=CATALOG),
        channel="chat",
        session_id="s",
        git_sha="g",
        project_version="v",
        adapters={"agenda": agenda},
    )
    tc.tools = LocalExecutor(tc)
    return tc


def rebooking(tc: TenantContext) -> Saga:
    return (
        Saga(tc)
        .step("cancel_slot", {"appointment_id": "old"})
        .step("book_slot", {"slot": "new"})
        .step("send_sms", {"phone": "600", "text": "hecho"})
    )


async def test_all_steps_run_in_order_and_return_their_results() -> None:
    agenda = Agenda()
    tc = context(agenda)
    confirm.mint(tc, "book_slot", {"slot": "new"})

    results = await rebooking(tc).run()

    assert [c[0] for c in agenda.calls] == ["cancel_slot", "book_slot", "send_sms"]
    assert results[1] == {"ok": True, "id": "book_slot-1"}


async def test_when_book_fails_the_cancel_is_compensated_and_the_failure_names_the_step() -> None:
    agenda = Agenda(failing="book_slot")
    tc = context(agenda)
    confirm.mint(tc, "book_slot", {"slot": "new"})

    with pytest.raises(SagaFailed) as failure:
        await rebooking(tc).run()

    assert failure.value.step == "book_slot"
    assert failure.value.compensated == ["cancel_slot"]
    assert agenda.calls[-1] == ("rebook_slot", {"appointment_id": "old"})


async def test_a_refused_step_compensates_too_and_never_reaches_the_adapter() -> None:
    agenda = Agenda()
    tc = context(agenda)  # no confirmation token: book_slot is vetoed by the guard

    with pytest.raises(SagaFailed) as failure:
        await rebooking(tc).run()

    assert failure.value.step == "book_slot"
    assert [c[0] for c in agenda.calls] == ["cancel_slot", "rebook_slot"]


async def test_completed_steps_are_undone_last_first_with_undo_args_from_their_result() -> None:
    agenda = Agenda(failing="send_sms")
    tc = context(agenda)
    confirm.mint(tc, "book_slot", {"slot": "new"})
    saga = (
        Saga(tc)
        .step("cancel_slot", {"appointment_id": "old"})
        .step("book_slot", {"slot": "new"}, undo_args=lambda r: {"appointment_id": r["id"]})
        .step("send_sms", {"phone": "600", "text": "hecho"})
    )

    with pytest.raises(SagaFailed) as failure:
        await saga.run()

    assert failure.value.compensated == ["book_slot", "cancel_slot"]
    assert agenda.calls[-2] == ("cancel_slot", {"appointment_id": "book_slot-1"})
    assert agenda.calls[-1] == ("rebook_slot", {"appointment_id": "old"})
