"""The contracts instantiate and encode the rules the platform enforces later."""

import pytest

from core.context import Project, Tenant, TenantContext
from core.contracts import SessionMeta
from core.state.events import Event
from core.tools.contract import SideEffect, ToolSpec

pytestmark = pytest.mark.unit


def test_irreversible_tools_always_need_confirmation() -> None:
    spec = ToolSpec(name="book_slot", side_effect=SideEffect.IRREVERSIBLE)
    assert spec.needs_confirmation()


def test_read_tools_do_not_need_confirmation_unless_asked() -> None:
    assert not ToolSpec(name="find", side_effect=SideEffect.READ).needs_confirmation()
    asked = ToolSpec(name="find", side_effect=SideEffect.READ, requires_confirmation=True)
    assert asked.needs_confirmation()


def test_pii_scope_marks_arguments_to_mask() -> None:
    spec = ToolSpec(name="find_customer", side_effect=SideEffect.READ, pii_scope=frozenset({"dni"}))
    assert spec.masks("dni") and not spec.masks("date")


def test_session_meta_ignores_unknown_fields() -> None:
    meta = SessionMeta.model_validate({"tenant": "acme", "project": "p", "future": 1})
    assert meta.tenant == "acme" and meta.channel == "voice"


def test_tenant_context_label() -> None:
    tenant = Tenant(id="acme", name="Acme")
    project = Project(id="p", name="P")
    tc = TenantContext(tenant, project, "chat", "s1", "abc", "git:abc")
    assert tc.label() == "acme/p#s1"


def test_event_summary_is_one_line() -> None:
    assert Event(seq=1, kind="session.start", t_ms=0).summary() == "   1       0ms session.start"
