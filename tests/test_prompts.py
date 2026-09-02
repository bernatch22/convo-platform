"""The clinic's stage prompts are composed from shared partials, never copied.

A rescheduling and a new booking are two conversations with one middle, and a
paragraph written twice drifts. So `prompts/_reception/*.md` holds the shared
blocks and each view includes them. What this suite pins is that the
composition really is composition: every shared partial appears in the views
that need it word for word and exactly once, in the declared order, and stays
out of the stages whose tools it would mislead (docs/decisions/003-shared-prompt-partials.md).

No key, no network, milliseconds. `pytest -m unit`.
"""

import re
from pathlib import Path

import pytest

from convo.prompting import includes, render
from convo.prompting.render import partial

pytestmark = pytest.mark.unit

PROMPTS = Path("tenants/clinica-norte/projects/reagendamiento/prompts")
SHARED = [
    "_reception/speaks_to_the_patient.md",
    "_reception/never_answers_without_the_agenda.md",
    "_reception/a_named_day_is_always_a_lookup.md",
    "_reception/offers_what_came_back.md",
    "_reception/the_tool_asks_for_the_yes.md",
    "_reception/says_hours_the_way_people_do.md",
    "_reception/only_the_hours_the_agenda_gave.md",
    "_reception/outside_the_appointment.md",
]
BOOKING_VIEWS = ("choose_slot", "new_booking")
CONFIRM_VIEWS = ("confirm/move", "confirm/new_booking", "confirm/contact", "confirm/cancellation")


def paragraphs(view: str) -> list[str]:
    """The paragraphs of a rendered view's <instructions> block, in order."""
    block = re.search(r"<instructions>\n(.*?)\n</instructions>", render(PROMPTS, view), re.S)
    assert block, f"{view} has no <instructions> block"
    return block.group(1).split("\n\n")


def shared(name: str) -> str:
    """The rendered text of one shared partial."""
    return partial(PROMPTS, name)


@pytest.mark.parametrize("name", SHARED)
def test_every_shared_paragraph_reaches_both_booking_stages_word_for_word(name: str) -> None:
    for view in BOOKING_VIEWS:
        assert shared(name) in render(PROMPTS, view)


@pytest.mark.parametrize("name", SHARED)
def test_no_shared_paragraph_was_left_behind_as_a_second_copy(name: str) -> None:
    """A re-inlined block would appear in the view source itself, and twice when rendered."""
    for view in BOOKING_VIEWS:
        assert render(PROMPTS, view).count(shared(name)) == 1
        assert shared(name) not in (PROMPTS / f"{view}.md").read_text()


def test_the_thursday_lesson_is_one_paragraph_and_both_stages_read_it() -> None:
    """The rule that cost a card to learn: a day the caller names is always a lookup."""
    lesson = shared("_reception/a_named_day_is_always_a_lookup.md")

    assert "en cuanto el paciente nombre uno, consulta y ofrece" in lesson
    assert all(lesson in render(PROMPTS, view) for view in BOOKING_VIEWS)


def test_choose_slot_includes_exactly_these_partials_in_this_order() -> None:
    assert includes(PROMPTS, "choose_slot") == [
        "_reception/speaks_to_the_patient.md",
        "_reception/never_answers_without_the_agenda.md",
        "_reception/a_named_day_is_always_a_lookup.md",
        "_reception/offers_what_came_back.md",
        "_reception/the_tool_asks_for_the_yes.md",
        "_reception/says_hours_the_way_people_do.md",
        "_reception/only_the_hours_the_agenda_gave.md",
        "_reception/outside_the_appointment.md",
    ]
    assert len(paragraphs("choose_slot")) == 11


def test_new_booking_includes_exactly_these_partials_in_this_order() -> None:
    assert includes(PROMPTS, "new_booking") == [
        "_reception/speaks_to_the_patient.md",
        "_reception/never_answers_without_the_agenda.md",
        "_reception/a_named_day_is_always_a_lookup.md",
        "_reception/offers_what_came_back.md",
        "_reception/the_tool_asks_for_the_yes.md",
        "_reception/says_hours_the_way_people_do.md",
        "_reception/only_the_hours_the_agenda_gave.md",
        "_reception/outside_the_appointment.md",
    ]
    assert len(paragraphs("new_booking")) == 10


def test_what_each_stage_owns_alone_stays_out_of_the_other() -> None:
    """The whole reason these are two stages: a cita to release, or nothing to fall back on."""
    choose_slot, new_booking = (render(PROMPTS, view) for view in BOOKING_VIEWS)

    assert "su cita anterior sigue en pie" in choose_slot
    assert "su cita anterior sigue en pie" not in new_booking
    assert "no le queda ninguna cita apuntada" in new_booking
    assert "no le queda ninguna cita apuntada" not in choose_slot


@pytest.mark.parametrize("view", CONFIRM_VIEWS)
def test_no_confirmation_prompt_tutea_the_patient_it_is_about_to_write_for(view: str) -> None:
    """ConfirmTask runs with its own tiny prompt, so the register has to travel with it."""
    confirm = render(PROMPTS, view)

    assert "de usted" in confirm
    assert "{question}" in confirm, "the platform renders the sentence, not the model"


def test_the_contact_stage_shares_how_the_clinic_speaks_and_nothing_about_the_agenda() -> None:
    """The one stage that never reads the agenda carries no rule about a tool it lacks."""
    assert includes(PROMPTS, "update_contact") == [
        "_reception/speaks_to_the_patient.md",
        "_reception/outside_the_appointment.md",
    ]
    assert len(paragraphs("update_contact")) == 6


def test_the_stage_that_changes_a_number_is_told_twice_never_to_read_one_out() -> None:
    """The rule the whole errand turns on, and the one a helpful model breaks unprompted."""
    block = render(PROMPTS, "update_contact")

    assert "solo puede confirmarse por las últimas cifras" in block
    assert "no tienes el resto" in block
    assert "600123456" not in block, "no real number belongs in a prompt about hiding them"


def test_the_hour_rule_is_shared_by_three_stages_and_the_booking_rule_by_two() -> None:
    """A stage that reads an hour back but books nothing needs one half of the old paragraph."""
    settling = includes(PROMPTS, "cancel_or_confirm")

    assert "_reception/says_hours_the_way_people_do.md" in settling
    assert "_reception/only_the_hours_the_agenda_gave.md" not in settling
    for view in BOOKING_VIEWS:
        assert "_reception/only_the_hours_the_agenda_gave.md" in includes(PROMPTS, view)


def test_the_settling_stage_includes_exactly_these_partials_in_this_order() -> None:
    assert includes(PROMPTS, "cancel_or_confirm") == [
        "_reception/speaks_to_the_patient.md",
        "_reception/says_hours_the_way_people_do.md",
        "_reception/outside_the_appointment.md",
    ]
    assert len(paragraphs("cancel_or_confirm")) == 9


def test_the_stage_that_cancels_is_told_the_cita_is_looked_up_and_never_recited() -> None:
    """The rule the whole errand turns on: a cita read off a note has no source in the call."""
    block = "\n\n".join(paragraphs("cancel_or_confirm"))

    assert "antes de decir nada de ella" in block
    assert "Ni el día, ni la hora, ni el profesional salen de tu cabeza." in block
    assert "Dra. Irene Campos" not in block, "no real appointment belongs in the instructions"


def test_the_two_verbs_are_told_apart_in_the_prompt_that_owns_them_both() -> None:
    """One stage, two verbs: what parts them is a sentence, and it has to be in there."""
    block = render(PROMPTS, "cancel_or_confirm")

    assert "Anular no se deshace" in block
    assert "no se le quita nada" in block
