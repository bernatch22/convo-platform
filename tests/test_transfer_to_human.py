"""transfer_to_human: a tool that cannot work is not offered, and the console owns the number."""

import pytest

from convo.session import pipeline
from convo.state.store import MemoryStore, PipelineOverride
from convo.telephony import human
from convo.testing import fake_context
from tests.fixtures.handover import (
    CLINIC,
    SHOP,
    SWITCHBOARD,
    _without_the_spec,
    tc,  # noqa: F401  (fixtures)
    tool_names,
)

pytestmark = pytest.mark.unit


# ── 1. a tool that cannot work is not offered ────────────────────────────────


def test_a_project_with_a_number_shows_the_verb_on_every_stage_of_the_call(tc) -> None:
    for stage in tc.project.stages(tc):
        assert human.TOOL in tool_names(stage), f"{stage.stage_name()} cannot hand the call on"


def test_a_project_with_no_number_never_shows_the_model_the_verb_at_all() -> None:
    shop = fake_context(*SHOP)

    for stage in shop.project.stages(shop):
        assert human.TOOL not in tool_names(stage)


def test_the_project_that_declares_no_spec_is_told_that_no_number_would_help(tc) -> None:
    assert human.unavailable(_without_the_spec(tc.project)) == human.NOT_DECLARED


def test_the_paragraph_that_teaches_the_verb_arrives_and_leaves_with_it(tc) -> None:
    shop = fake_context(*SHOP)

    assert human.protocol(tc.project) == human.PROTOCOL
    assert human.protocol(shop.project) == human.ALONE, "silence is not honesty"


def test_a_project_that_never_asked_the_question_is_told_nothing_about_transfers(tc) -> None:
    """Core invents no policy for a business that did not declare the verb."""
    tc.project = _without_the_spec(tc.project)

    assert human.protocol(tc.project) == ""


def test_the_clinic_prompt_teaches_the_announcement_and_the_shop_prompt_teaches_the_truth(
    tc,
) -> None:
    """A shop with nobody to pass a call to must not answer «ahora mismo te paso» (2026-08-31)."""
    shop = fake_context(*SHOP)
    clinic_prompt = tc.project.entry_agent(tc).instructions
    shop_prompt = shop.project.entry_agent(shop).instructions

    assert "le paso con un compañero" in clinic_prompt
    assert human.TOOL not in shop_prompt, "a rule about a tool it lacks makes it reach for one"
    assert "no hay nadie más a quien pasar la llamada" in shop_prompt


# ── 2. the console owns the number ───────────────────────────────────────────


def test_the_console_may_set_the_number_and_the_platform_says_which_ones_it_runs() -> None:
    assert pipeline.overridable(human.FIELD, SWITCHBOARD) is None
    assert pipeline.overridable(human.FIELD, "") is None, "empty takes the verb away"
    for bad in ("910000000", "+34 910 000 000", "recepción", "ext 204"):
        assert "E.164" in (pipeline.overridable(human.FIELD, bad) or "")


def test_the_pipeline_screen_shows_the_number_and_says_the_verb_is_live(tc) -> None:
    view = pipeline.snapshot(tc.tenant, tc.project, MemoryStore())["phone"]["transfer"]

    assert view["number"] == SWITCHBOARD
    assert view["offered"] is True
    assert view["unavailable_reasons"] == {}


def test_a_project_with_no_number_is_greyed_out_with_the_reason_in_the_servers_words() -> None:
    shop = fake_context(*SHOP)

    view = pipeline.snapshot(shop.tenant, shop.project, MemoryStore())["phone"]["transfer"]

    assert view["offered"] is False
    assert view["unavailable_reasons"] == {human.TOOL: human.NO_NUMBER}
    assert view["note"] == human.NO_NUMBER


async def test_clearing_the_number_from_the_console_takes_the_verb_off_the_next_session() -> None:
    from convo.state import overrides

    tc = fake_context(*CLINIC)
    store = MemoryStore()
    store.set_pipeline_override(PipelineOverride(tc.tenant.id, tc.project.id, human.FIELD, ""))

    cleared = overrides.apply(tc.tenant.id, tc.project, store)

    assert human.number_of(cleared) == ""
    assert human.offered(cleared) is False
