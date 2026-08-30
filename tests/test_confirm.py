"""The confirmation token: one yes authorises one call, once, for a couple of minutes."""

import pytest

from core import confirm
from core.tools.guard import ToolRefused
from tests.test_tools import FakeAdapter, context

pytestmark = pytest.mark.unit

CANCEL = "cancel_appointment"
ARGS = {"phone": "600123456"}


async def test_an_irreversible_call_is_refused_without_any_token() -> None:
    adapter = FakeAdapter()
    tc = context(adapter)

    with pytest.raises(ToolRefused, match="no confirmation token"):
        await tc.tools.call(CANCEL, ARGS)
    assert adapter.calls == []


async def test_a_token_minted_for_other_arguments_is_refused() -> None:
    adapter = FakeAdapter()
    tc = context(adapter)
    confirm.mint(tc, CANCEL, {"phone": "699000000"})

    with pytest.raises(ToolRefused, match="another call"):
        await tc.tools.call(CANCEL, ARGS)
    assert adapter.calls == []


async def test_a_token_minted_for_another_tool_is_refused() -> None:
    tc = context(FakeAdapter())
    confirm.mint(tc, "find_availability", ARGS)

    with pytest.raises(ToolRefused, match="another call"):
        await tc.tools.call(CANCEL, ARGS)


async def test_the_right_token_passes_once_and_is_spent_by_the_call() -> None:
    adapter = FakeAdapter()
    tc = context(adapter)
    confirm.mint(tc, CANCEL, ARGS)

    await tc.tools.call(CANCEL, ARGS)
    with pytest.raises(ToolRefused, match="already spent"):
        await tc.tools.call(CANCEL, ARGS)

    assert [c[0] for c in adapter.calls] == [CANCEL]


async def test_an_expired_token_is_refused() -> None:
    tc = context(FakeAdapter())
    token = confirm.mint(tc, CANCEL, ARGS, ttl_s=0.0)
    token.minted_at -= 1

    with pytest.raises(ToolRefused, match="expired"):
        await tc.tools.call(CANCEL, ARGS)


def test_the_audience_ignores_argument_order_but_not_values() -> None:
    assert confirm.audience("t", {"a": 1, "b": 2}) == confirm.audience("t", {"b": 2, "a": 1})
    assert confirm.audience("t", {"a": 1}) != confirm.audience("t", {"a": 2})


async def test_a_read_tool_never_spends_the_token() -> None:
    tc = context(FakeAdapter())
    token = confirm.mint(tc, CANCEL, ARGS)

    await tc.tools.call("find_availability", {"date": "2026-09-01"})

    assert token.used is False
