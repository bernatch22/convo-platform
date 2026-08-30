"""What the agent claimed and what the call could back it up with — the free half of an eval.

Every rule here used to be a sentence in a GEval criterion, judged by a model
that could not see the clinic's price list and scored the same correct answer
0.0 on one run and 0.9 on the next. They are assertions now, and they cost
nothing to run, which is why the DAG that uses them can score every golden of
the suite instead of the two somebody remembered to check.

Fake turns rather than real ones: a conversation with Haiku costs seconds and
moves between runs, and none of that is needed to prove that «90 euros» is in
the clinic's sheet and «500 euros» is not.
"""

import importlib
from dataclasses import dataclass, field

import pytest
from deepeval.test_case import ToolCall

pytestmark = pytest.mark.unit

grounding = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.evals.grounding")


@dataclass
class FakeTurn:
    """Enough of a deepeval Turn for the grounding functions: who spoke, what they said."""

    role: str
    content: str
    tools_called: list[ToolCall] = field(default_factory=list)


def said(text: str, tools: list[ToolCall] | None = None) -> FakeTurn:
    return FakeTurn(role="assistant", content=text, tools_called=tools or [])


def asked(text: str) -> FakeTurn:
    return FakeTurn(role="user", content=text)


def kinds(turns: list[FakeTurn]) -> list[str]:
    return [datum.kind for datum in grounding.stated_data(turns)]


def leftover(turns: list[FakeTurn]) -> list[str]:
    data = grounding.stated_data(turns)
    return [datum.said for datum in grounding.unsupported(data, grounding.evidence_of(turns))]


# --- what counts as a checkable fact ----------------------------------------


def test_a_reply_that_states_no_number_and_no_name_states_nothing_to_check() -> None:
    """A policy is not a fact: «se pueden cambiar» has nobody to be wrong about."""
    assert kinds([said("Claro, las citas se cambian sin problema. ¿Qué día le viene bien?")]) == []


def test_hours_prices_professionals_phones_and_addresses_are_what_gets_checked() -> None:
    turns = [
        said(
            "Le atiende la Dra. Irene Campos a las 14:00 en Calle del Norte 12; la revisión "
            "son 60 euros y el teléfono del centro es el 910 000 000."
        )
    ]

    assert set(kinds(turns)) == {"hora", "precio", "profesional", "teléfono", "dirección"}


def test_an_hour_said_out_loud_is_read_as_the_hour_it_means() -> None:
    """The platform reads a confirmation as «las nueve de la mañana»; the agenda wrote 09:00."""
    data = grounding.stated_data([said("Le confirmo las nueve de la mañana, ¿de acuerdo?")])

    assert data[0].keys == ("09:00",)


def test_the_part_of_the_day_is_what_settles_nine_from_twenty_one() -> None:
    evening = grounding.stated_data([said("Le queda a las nueve de la noche.")])
    lunchtime = grounding.stated_data([said("Le queda a la una de la tarde.")])

    assert evening[0].keys == ("21:00",)
    assert lunchtime[0].keys == ("13:00",)


def test_two_o_clock_only_counts_as_an_hour_when_it_says_which_two_o_clock() -> None:
    """«las dos horas» is a count, not a time, and a regex cannot tell without the suffix."""
    assert kinds([said("Le ofrezco las dos horas que me quedan libres.")]) == []
    assert kinds([said("Le ofrezco las dos de la tarde.")]) == ["hora"]


def test_the_same_hour_repeated_in_one_reply_is_one_fact() -> None:
    turns = [said("A las 11:00, sí, las 11:00 con la doctora.")]

    assert kinds(turns) == ["hora"]


# --- what grounds it --------------------------------------------------------


def test_a_price_from_the_clinic_s_own_sheet_needs_no_tool_behind_it() -> None:
    """The answer the old GEval failed for «inventing» a price it had in front of it."""
    assert leftover([asked("¿cuánto cuesta?"), said("La primera consulta son 90 euros.")]) == []


def test_a_price_that_is_on_no_sheet_is_left_over_for_the_judge() -> None:
    assert leftover([said("La primera consulta son 500 euros.")]) == ["500 euros"]


def test_an_hour_the_agenda_returned_this_turn_is_grounded_by_the_tool_output() -> None:
    offered = ToolCall(
        name="find_availability",
        output="Huecos libres:\n- jueves 3 de septiembre a las 09:00, Dr. Hugo Ferrer",
    )

    assert leftover([said("Le queda el jueves a las 09:00 con Dr. Hugo Ferrer.", [offered])]) == []


def test_an_hour_the_agenda_never_returned_is_left_over() -> None:
    offered = ToolCall(name="find_availability", output="Huecos: a las 09:00, Dr. Hugo Ferrer")

    assert leftover([said("Le queda a las 16:30.", [offered])]) == ["16:30"]


def test_the_clinic_writing_eight_and_the_agent_writing_zero_eight_are_the_same_hour() -> None:
    """The sheet says «de 8:00 a 20:00»; a reply saying 08:00 has not invented anything."""
    assert leftover([said("Abrimos de 08:00 a 20:00.")]) == []


def test_a_phone_number_the_patient_read_out_is_grounded_by_the_patient() -> None:
    """The caller is a source: repeating back what they just said is not an invention."""
    turns = [asked("mi teléfono es el 600123456"), said("Anotado, el 600 123 456.")]

    assert leftover(turns) == []


def test_the_agent_s_own_earlier_reply_is_never_evidence_for_its_later_one() -> None:
    """Otherwise an invention launders itself one turn later by being repeated."""
    turns = [said("Le queda a las 16:30."), asked("¿cómo dice?"), said("A las 16:30.")]

    assert leftover(turns) == ["16:30"]


def test_the_hour_of_the_cita_the_patient_already_had_is_grounded_by_the_lookup() -> None:
    """The miss that failed two goldens: the platform recorded `executed` and dropped the row.

    `find_patient` answers with the appointment the caller already has, the
    agent reads it back — `el jueves 3 a las 10:00` — and nothing else in the
    call contains that hour. Two things had to be true for it to match: the
    platform call carries its RESULT, and an hour is recognised inside an ISO
    timestamp, where there is no word boundary between the `T` and the `1`.
    """
    found = ToolCall(
        name="find_patient",
        output="{'when': '2026-09-03T10:00', 'doctor': 'Dra. Irene Campos'}",
    )
    turns = [
        asked("soy Ana García Ruiz"),
        said("Tiene cita el jueves 3 a las 10:00 con la Dra. Irene Campos.", [found]),
    ]

    assert leftover(turns) == []
