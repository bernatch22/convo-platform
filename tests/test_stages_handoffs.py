"""What each stage says to the next, and how an hour is matched and spoken."""

import pytest

from tests.fixtures.clinic import (  # noqa: F401  (fixtures)
    REFUSED_13,
    THURSDAY_11,
    booking,
    choosing,
    helpers_module,
    stages,
    tc,
    unknown,
)

pytestmark = pytest.mark.unit


# --- what each stage says to the next ---------------------------------------


def test_the_hour_the_caller_says_is_matched_however_they_say_it() -> None:
    """Shared by both booking stages, which is why it lives in `tools` and not in either."""
    assert helpers_module.normalise_hour("11:00") == "11:00"
    assert helpers_module.normalise_hour("9") == "09:00"
    assert helpers_module.normalise_hour("las 16.30") == "16:30"
    assert helpers_module.normalise_hour("a media tarde") == ""
    assert helpers_module.hour_of("2026-09-03T11:00") == "11:00"


def test_the_confirmation_sentence_says_the_hour_the_way_a_person_says_it() -> None:
    """It is read out verbatim, so «13:00» would be spoken «las trece cero cero»."""
    said = helpers_module.confirmation_question(REFUSED_13)

    assert said == "martes 8 de septiembre a la una de la tarde con Dra. Campos, ¿lo confirmo?"


def test_identify_hands_the_next_stage_the_patient_and_the_cita_they_already_have(tc) -> None:
    summary = stages.Identify(tc).summary()

    assert "Ana García Ruiz" in summary
    assert "jueves 3 de septiembre a las 10:00" in summary


def test_identify_tells_the_next_stage_when_the_caller_has_no_cita_at_all(unknown) -> None:
    """The one sentence that sends NewBooking down its own path instead of ChooseSlot's."""
    summary = stages.Identify(unknown).summary()

    assert "Pedro Ramos Gil" in summary
    assert "No consta ninguna cita" in summary


def test_new_booking_hands_the_farewell_the_cita_it_has_just_created(unknown) -> None:
    stage = booking(unknown)
    assert "Todavía no" in stage.summary()

    stage.booked = THURSDAY_11
    assert "jueves 3 de septiembre a las 11:00" in stage.summary()


def test_choose_slot_hands_the_farewell_the_appointment_that_now_exists(tc) -> None:
    stage = choosing(tc)
    assert "Todavía no" in stage.summary()

    stage.booked = THURSDAY_11
    assert "jueves 3 de septiembre a las 11:00" in stage.summary()
