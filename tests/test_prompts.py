"""The clinic's two booking prompts are composed from shared paragraphs, never copied.

A rescheduling and a new booking are two conversations with one middle, and the
middle is the expensive half to get right: the Thursday lesson (a day the caller
names is ALWAYS a lookup) took a call and a card to learn. Written twice, that
paragraph drifts — one copy learns the next lesson and the other keeps the old
wording — and no metric can see it happen, because both copies are "the prompt".

So `prompts/reception.py` holds the shared blocks and each stage composes. What
this suite pins is that the composition really is composition: every shared block
appears in both stages, word for word and exactly once, and each stage's
assembled instructions are the paragraphs it declares, in order, with nothing
smuggled in between.

The split itself was made byte-identical: `CHOOSE_SLOT_INSTRUCTIONS` after it was
the same 4787 characters it was before, which is what let ms-18 add a stage
without moving the ring underneath the existing goldens. It is longer than that
now, by one sentence that ms-18's Sunday golden earned — and that sentence
reached BOTH stages because it went into a shared block. That is a fact about two
commits and cannot be asserted afterwards; what CAN be asserted is everything
below, and it is what would break if somebody re-inlined a block.

No key, no network, milliseconds. `pytest -m unit`.
"""

import importlib

import pytest

pytestmark = pytest.mark.unit

PROMPTS = "tenants.clinica-norte.projects.reagendamiento.prompts"

reception = importlib.import_module(f"{PROMPTS}.reception")
choose_slot = importlib.import_module(f"{PROMPTS}.choose_slot")
new_booking = importlib.import_module(f"{PROMPTS}.new_booking")
update_contact = importlib.import_module(f"{PROMPTS}.update_contact")

SHARED = (
    reception.SPEAKS_TO_THE_PATIENT,
    reception.NEVER_ANSWERS_WITHOUT_THE_AGENDA,
    reception.A_NAMED_DAY_IS_ALWAYS_A_LOOKUP,
    reception.OFFERS_WHAT_CAME_BACK,
    reception.THE_TOOL_ASKS_FOR_THE_YES,
    reception.SAYS_HOURS_THE_WAY_PEOPLE_DO,
    reception.OUTSIDE_THE_APPOINTMENT,
)
BOTH_STAGES = (choose_slot.CHOOSE_SLOT_INSTRUCTIONS, new_booking.NEW_BOOKING_INSTRUCTIONS)


def paragraphs(block: str) -> list[str]:
    """The paragraphs of an <instructions> block, as `instructions()` joined them."""
    inner = block.removeprefix(reception.OPEN + "\n").removesuffix("\n" + reception.CLOSE + "\n")
    return inner.split("\n\n")


@pytest.mark.parametrize("shared", SHARED, ids=lambda text: text[:40])
def test_every_shared_paragraph_reaches_both_booking_stages_word_for_word(shared: str) -> None:
    for block in BOTH_STAGES:
        assert shared in block


@pytest.mark.parametrize("shared", SHARED, ids=lambda text: text[:40])
def test_no_shared_paragraph_was_left_behind_as_a_second_copy(shared: str) -> None:
    """A re-inlined block would still contain the text — and would contain it twice."""
    for block in BOTH_STAGES:
        assert block.count(shared) == 1


def test_the_thursday_lesson_is_one_paragraph_and_both_stages_read_it() -> None:
    """The rule that cost a card to learn: a day the caller names is always a lookup."""
    lesson = reception.A_NAMED_DAY_IS_ALWAYS_A_LOOKUP

    assert "en cuanto el paciente nombre uno, consulta y ofrece" in lesson
    assert all(lesson in block for block in BOTH_STAGES)


def test_choose_slot_is_exactly_the_paragraphs_it_declares_in_that_order() -> None:
    assert paragraphs(choose_slot.CHOOSE_SLOT_INSTRUCTIONS) == [
        reception.SPEAKS_TO_THE_PATIENT,
        choose_slot.ALREADY_IDENTIFIED,
        reception.NEVER_ANSWERS_WITHOUT_THE_AGENDA,
        reception.A_NAMED_DAY_IS_ALWAYS_A_LOOKUP,
        choose_slot.HER_OWN_DAY_IS_NO_EXCEPTION,
        reception.OFFERS_WHAT_CAME_BACK,
        reception.THE_TOOL_ASKS_FOR_THE_YES,
        reception.SAYS_HOURS_THE_WAY_PEOPLE_DO,
        choose_slot.WHAT_THE_BOOKING_TOOL_SAID,
        reception.OUTSIDE_THE_APPOINTMENT,
    ]


def test_new_booking_is_exactly_the_paragraphs_it_declares_in_that_order() -> None:
    assert paragraphs(new_booking.NEW_BOOKING_INSTRUCTIONS) == [
        reception.SPEAKS_TO_THE_PATIENT,
        new_booking.NOTHING_ON_THE_BOOK_YET,
        reception.NEVER_ANSWERS_WITHOUT_THE_AGENDA,
        reception.A_NAMED_DAY_IS_ALWAYS_A_LOOKUP,
        reception.OFFERS_WHAT_CAME_BACK,
        reception.THE_TOOL_ASKS_FOR_THE_YES,
        reception.SAYS_HOURS_THE_WAY_PEOPLE_DO,
        new_booking.WHAT_THE_BOOKING_TOOL_SAID,
        reception.OUTSIDE_THE_APPOINTMENT,
    ]


def test_what_each_stage_owns_alone_stays_out_of_the_other() -> None:
    """The whole reason these are two stages: a cita to release, or nothing to fall back on."""
    assert choose_slot.HER_OWN_DAY_IS_NO_EXCEPTION not in new_booking.NEW_BOOKING_INSTRUCTIONS
    assert new_booking.NOTHING_ON_THE_BOOK_YET not in choose_slot.CHOOSE_SLOT_INSTRUCTIONS
    assert "su cita anterior sigue en pie" in choose_slot.WHAT_THE_BOOKING_TOOL_SAID
    assert "no le queda ninguna cita apuntada" in new_booking.WHAT_THE_BOOKING_TOOL_SAID


def test_no_confirmation_prompt_tutea_the_patient_it_is_about_to_write_for() -> None:
    """ConfirmTask runs with its own tiny prompt, so the register has to travel with it."""
    for confirm in (
        choose_slot.CONFIRM_INSTRUCTIONS,
        new_booking.CONFIRM_NEW_BOOKING_INSTRUCTIONS,
        update_contact.CONFIRM_CONTACT_INSTRUCTIONS,
    ):
        assert "de usted" in confirm
        assert "{question}" in confirm, "the platform renders the sentence, not the model"


def test_the_contact_stage_shares_how_the_clinic_speaks_and_nothing_about_the_agenda() -> None:
    """It is the one stage that never reads the agenda, so the agenda paragraphs stay out.

    Composition is not a reflex here: three of the shared blocks are about
    consulting a diary, and a stage that cannot book anything would be carrying
    rules for tools it does not have — the surest way to have a model reach for
    one.
    """
    block = update_contact.UPDATE_CONTACT_INSTRUCTIONS

    assert reception.SPEAKS_TO_THE_PATIENT in block
    assert reception.OUTSIDE_THE_APPOINTMENT in block
    assert reception.NEVER_ANSWERS_WITHOUT_THE_AGENDA not in block
    assert reception.A_NAMED_DAY_IS_ALWAYS_A_LOOKUP not in block
    assert reception.OFFERS_WHAT_CAME_BACK not in block


def test_the_contact_stage_is_exactly_the_paragraphs_it_declares_in_that_order() -> None:
    assert paragraphs(update_contact.UPDATE_CONTACT_INSTRUCTIONS) == [
        reception.SPEAKS_TO_THE_PATIENT,
        update_contact.THE_NUMBER_ON_FILE_IS_NEVER_READ_OUT,
        update_contact.VALIDATE_FIRST_THEN_TAKE_THE_NEW_ONE,
        update_contact.THE_CONTACT_TOOL_ASKS_FOR_THE_YES,
        update_contact.WHAT_THE_CONTACT_TOOL_SAID,
        reception.OUTSIDE_THE_APPOINTMENT,
    ]


def test_the_stage_that_changes_a_number_is_told_twice_never_to_read_one_out() -> None:
    """The rule the whole errand turns on, and the one a helpful model breaks unprompted."""
    block = update_contact.UPDATE_CONTACT_INSTRUCTIONS

    assert "solo puede confirmarse por las últimas cifras" in block
    assert "no tienes el resto" in block
    assert "600123456" not in block, "no real number belongs in a prompt about hiding them"
