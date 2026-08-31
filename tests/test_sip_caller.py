"""core.sip: finding the phone caller of a room job, and the number they dialled."""

import pytest

from core import sip
from core.testing.fake_job import fake_job_context

pytestmark = pytest.mark.unit

DIALLED = {"sip.trunkPhoneNumber": "+14176743169", "sip.callID": "abc"}


async def test_a_participant_job_carries_the_caller_on_the_job() -> None:
    ctx = fake_job_context(participant_attributes=DIALLED)

    assert await sip.caller_attributes(ctx) == DIALLED


async def test_a_room_job_finds_the_caller_among_the_room_participants() -> None:
    ctx = fake_job_context(room_participants=DIALLED)

    assert await sip.caller_attributes(ctx) == DIALLED


async def test_only_the_sip_attributes_of_a_caller_are_kept() -> None:
    ctx = fake_job_context(room_participants={**DIALLED, "lk.agent": "cc"})

    assert await sip.caller_attributes(ctx) == DIALLED


async def test_a_job_with_no_caller_and_nobody_to_wait_for_reads_empty() -> None:
    assert await sip.caller_attributes(fake_job_context()) == {}


def test_the_trunk_number_is_preferred_over_the_caller_id() -> None:
    both = {"sip.phoneNumber": "+34600111222", "sip.trunkPhoneNumber": "+14176743169"}

    assert sip.dialled_number(both) == "+14176743169"


def test_a_call_with_no_number_at_all_has_nothing_to_route_on() -> None:
    assert sip.dialled_number({"sip.callID": "abc"}) is None


def test_the_wait_budget_is_tunable_and_falls_back_when_it_is_nonsense(monkeypatch) -> None:
    monkeypatch.setenv(sip.WAIT_ENV, "0.5")
    assert sip.wait_budget() == 0.5

    monkeypatch.setenv(sip.WAIT_ENV, "soon")
    assert sip.wait_budget() == sip.DEFAULT_WAIT_S
