"""The business view: the reservations themselves, and the call each one came out of.

`/outcomes` counts what the platform did; this counts nothing. It asks the
customer's own system for its records and joins them to the log by the one
thing the PII mask lets through — the identifier. So the cases here are: the
adapter's shape travels whole, a project with no such view says so instead of
inventing one, a booking written in a session is visible to a second process,
and the join finds the call without either side knowing the other's vocabulary.
"""

import time
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from convo.adapters.base import LIST_RECORDS, PLAIN, Adapter
from convo.adapters.ledger import Ledger
from convo.api.app import app, open_store
from convo.domain import business
from convo.domain.context import Project, Tenant
from convo.state.events import Event
from convo.state.store import MemoryStore, SessionRow

pytestmark = pytest.mark.unit

SESSION = "sess-booked"
SUMMARY = "appointment ap-20260904-1000-trau now 2026-09-04T10:00"


class OneRecord(Adapter):
    """A tenant system with exactly one record, in a shape core has never heard of."""

    def capabilities(self) -> list[str]:
        return [LIST_RECORDS]

    async def execute(self, capability: str, args: dict) -> dict:
        return {
            "shape": "kennels",
            "labels": {"who": "owner", "handled_by": "vet", "when": "stay"},
            "rows": [
                {
                    "id": "ap-20260904-1000-trau",
                    "who": "Ana García Ruiz",
                    "contact": "600123456",
                    "when": "2026-09-04T10:00",
                    "handled_by": "Dra. Irene Campos",
                    "state": "moved",
                    "tone": "changed",
                    "detail": "traumatología",
                    "at": time.time(),
                }
            ],
        }


class Silent(Adapter):
    """A tenant system with no view to offer the console at all."""

    def capabilities(self) -> list[str]:
        return ["send_sms"]

    async def execute(self, capability: str, args: dict) -> None:
        return None


def tenant_with(*adapters: Adapter) -> Tenant:
    """A registry-shaped tenant whose factory hands back exactly these systems."""

    class Built(Tenant):
        def build_adapters(self) -> dict[str, Adapter]:
            return {f"sys{n}": adapter for n, adapter in enumerate(adapters)}

    return Built(id="clinica-norte", name="C", projects={"reagendamiento": Project("r", "R")})


def logged() -> MemoryStore:
    """One call that booked the appointment the adapter is about to report."""
    store = MemoryStore()
    store.open_session(
        SessionRow(SESSION, "clinica-norte", "reagendamiento", "voice", started_at=time.time() - 60)
    )
    store.append(SESSION, Event(1, "confirm.granted", 100, {"tool": "book_slot"}))
    store.append(
        SESSION, Event(2, "tool.call", 200, {"tool": "book_slot", "side_effect": "irreversible"})
    )
    store.append(SESSION, Event(3, "tool.result", 300, {"tool": "book_slot", "summary": SUMMARY}))
    return store


async def test_the_adapter_s_own_shape_and_labels_travel_whole() -> None:
    view = await business.records(tenant_with(OneRecord()), "reagendamiento", MemoryStore())

    assert view["shape"] == "kennels"
    assert view["labels"]["handled_by"] == "vet"
    assert view["rows"][0]["who"] == "Ana García Ruiz"
    assert view["rows"][0]["state"] == "moved"


async def test_a_tenant_with_no_business_view_answers_an_honest_empty() -> None:
    view = await business.records(tenant_with(Silent()), "reagendamiento", MemoryStore())

    assert view["shape"] is None
    assert view["rows"] == []


async def test_a_record_is_joined_to_the_call_that_last_touched_it() -> None:
    view = await business.records(tenant_with(Silent(), OneRecord()), "reagendamiento", logged())

    row = view["rows"][0]
    assert row["session"] == SESSION
    assert row["verb"] == "book_slot"
    assert row["confirmed"] is True


async def test_a_record_no_call_touched_carries_no_session() -> None:
    view = await business.records(tenant_with(OneRecord()), "reagendamiento", MemoryStore())

    assert view["rows"][0]["session"] is None
    assert view["rows"][0]["confirmed"] is False


async def test_a_booking_taken_in_one_process_is_read_by_another() -> None:
    """The whole point of the ledger: the console is never the process that took the call."""
    agenda = import_module("tenants.clinica-norte.adapters.agenda")
    took_the_call = agenda.FakeAgenda()
    await took_the_call.execute(
        "book_slot",
        {"slot_id": "sl-20260904-1000-trau", "patient": "Ana García Ruiz", "phone": "600123456"},
    )

    console = agenda.FakeAgenda()  # a second process: a book of its own, the same ledger
    rows = {row["id"]: row for row in (await console.execute(LIST_RECORDS, {}))["rows"]}

    assert rows["ap-20260904-1000-trau"]["who"] == "Ana García Ruiz"
    assert rows["ap-20260904-1000-trau"]["state"] == "created"


async def test_a_rescheduling_reads_as_one_moved_appointment() -> None:
    """Two irreversible calls to the platform; one moved cita to the clinic, which is the truth."""
    agenda = import_module("tenants.clinica-norte.adapters.agenda")
    book = agenda.FakeAgenda()
    await book.execute("cancel_slot", {"appointment_id": "ap-20260903-1000-trau"})
    await book.execute(
        "book_slot",
        {"slot_id": "sl-20260904-1000-trau", "patient": "Ana García Ruiz", "phone": "600123456"},
    )

    rows = {row["id"]: row for row in (await agenda.FakeAgenda().execute(LIST_RECORDS, {}))["rows"]}

    assert rows["ap-20260903-1000-trau"]["state"] == "cancelled"
    assert rows["ap-20260904-1000-trau"]["state"] == "moved"


async def test_the_shop_answers_orders_and_never_an_agenda() -> None:
    """A project with no appointments is not an empty agenda: it has records of its own."""
    orders = import_module("tenants.tienda-sur.adapters.orders")
    view = await orders.FakeOrders().execute(LIST_RECORDS, {})

    assert view["shape"] == "orders"
    assert view["labels"]["who"] == "customer"
    assert any(row["id"] == "TS-10432" for row in view["rows"])


async def test_the_endpoint_refuses_a_project_the_tenant_does_not_have() -> None:
    app.dependency_overrides[open_store] = lambda: MemoryStore()
    try:
        with TestClient(app) as client:
            answer = client.get("/reservations?tenant=clinica-norte&project=nope")
        assert answer.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_the_endpoint_answers_the_clinic_s_own_appointments() -> None:
    app.dependency_overrides[open_store] = lambda: logged()
    try:
        with TestClient(app) as client:
            answer = client.get("/reservations?tenant=clinica-norte&project=reagendamiento")
    finally:
        app.dependency_overrides.clear()

    body = answer.json()
    assert answer.status_code == 200
    assert body["shape"] == "appointments"
    assert body["labels"]["handled_by"] == "professional"
    assert all(row["tone"] in ("new", "changed", "gone", PLAIN) for row in body["rows"])


def test_the_ledger_survives_the_process_that_wrote_it(tmp_path) -> None:
    """A row written through one Ledger is read by a second one opened over the same file."""
    path = tmp_path / "business.json"
    Ledger("clinica-norte/agenda", path).record("ap-1", {"id": "ap-1", "state": "created"})

    assert Ledger("clinica-norte/agenda", path).rows()["ap-1"]["state"] == "created"
    assert Ledger("tienda-sur/orders", path).rows() == {}
