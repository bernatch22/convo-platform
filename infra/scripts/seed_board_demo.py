"""Write three REAL transactions into a store, so the Board has something to show.

Decisions: docs/decisions/infra.scripts.seed_board_demo.md
"""

import asyncio
import uuid
from datetime import date
from typing import Any

from convo.domain.context import TenantContext
from convo.session.registry import load_registry
from convo.state.attach import attach_log, close_log
from convo.state.log import record
from convo.state.store import SQLiteStore, Store
from convo.tools.confirm import mint
from convo.tools.executor import attach_local_tools

TODAY = date(2026, 8, 31)
PATIENTS = (("2026-09-03", "Bernardo Castro"), ("2026-09-04", "Lucía Ferrer"))
PHONE = "600111222"
ORDER = "TS-10432"


async def main() -> None:
    """Book two appointments in the clinic and cancel one order in the shop, for real."""
    store = SQLiteStore()

    for day, patient in PATIENTS:
        await book(store, day, patient)
    await cancel(store)


async def book(store: Store, day: str, patient: str) -> None:
    """One clinic call: read the agenda, take the caller's yes, write the booking."""
    tc = session(store, "clinica-norte", "reagendamiento")
    tc.customer = {"patient": patient, "phone": PHONE}
    free = await tc.tools.call("find_availability", {"date": day})
    if not free:
        return end(tc, "dropped")
    slot = free[0]
    await transact(
        tc,
        "book_slot",
        {
            "slot_id": slot["id"],
            "patient": patient,
            "phone": PHONE,
            "doctor": slot.get("doctor", ""),
        },
    )
    end(tc, "completed")


async def cancel(store: Store) -> None:
    """One shop call: the caller confirms, the order is stopped. `cancel_order` is irreversible."""
    tc = session(store, "tienda-sur", "pedidos")
    await transact(tc, "cancel_order", {"order_id": ORDER})
    end(tc, "completed")


async def transact(tc: TenantContext, tool: str, args: dict[str, Any]) -> None:
    """Say yes and then do it — the two log lines the Board pairs into one transaction."""
    mint(tc, tool, args)
    record(tc, "confirm.granted", {"tool": tool})
    result = await tc.tools.call(tool, args)
    print(f"{tc.session_id}  {tool} → {result}")


def session(store: Store, tenant_id: str, project_id: str) -> TenantContext:
    """A context wired exactly as `core.router.resolve` wires one, logging to this store."""
    tenant = load_registry()[tenant_id]
    tc = TenantContext(
        tenant=tenant,
        project=tenant.projects[project_id],
        channel="voice",
        session_id=f"demo-{uuid.uuid4().hex[:10]}",
        git_sha="demo",
        project_version="git:demo",
        today=TODAY,
    )
    return attach_log(attach_local_tools(tc), store)


def end(tc: TenantContext, outcome: str) -> None:
    """Close the session the way the observers do, so the call log reads normally too."""
    if tc.log is not None:
        tc.log.append("session.end", {"outcome": outcome, "cost": {"eur": 0.0}})
    close_log(tc, None)


if __name__ == "__main__":
    asyncio.run(main())
