"""The register check: two businesses, opposite rules, one word-boundary scan and no judge.

Clínica Norte addresses patients as "usted" and Tienda Sur tutea, and a single
slip either way is a defect with no degrees — a GEval asked about tone scores
it 0.8 and moves on. So it is a `DeterministicNode` over the forms each project
declares (`evals/dag.py`), and every rule below runs in microseconds.

The interesting half is the false positives: a scan that matched substrings
would find "te" inside "usted" and fail every correct clinic reply.
"""

import importlib
from dataclasses import dataclass

import pytest

from convo.testing.metrics.register import slips

pytestmark = pytest.mark.unit

clinica = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.evals.dag")
tienda = importlib.import_module("tenants.tienda-sur.projects.pedidos.evals.dag")


@dataclass
class FakeTurn:
    """Enough of a deepeval Turn for the scan: who spoke, and what they said."""

    role: str
    content: str


def said(text: str) -> FakeTurn:
    return FakeTurn(role="assistant", content=text)


def asked(text: str) -> FakeTurn:
    return FakeTurn(role="user", content=text)


def words(turns: list[FakeTurn], forbidden: tuple[str, ...]) -> list[str]:
    return [word for _, word in slips(turns, forbidden)]


# --- the clinic must never tutear -------------------------------------------


def test_a_clinic_reply_in_usted_uses_no_forbidden_form() -> None:
    turns = [said("Le queda el jueves a las once con la doctora Campos. ¿Se la confirmo?")]

    assert words(turns, clinica.TU_FORMS) == []


def test_the_tuteo_that_slipped_through_a_geval_in_ms_3_is_caught_here() -> None:
    """«¿Cuál te viene mejor?» appeared once in 21 cases and scored 0.8 as "good tone"."""
    turns = [said("Tengo las nueve y las doce. ¿Cuál te viene mejor?")]

    assert words(turns, clinica.TU_FORMS) == ["te"]


def test_usted_does_not_count_as_a_tuteo_because_it_contains_te() -> None:
    """The false positive a substring scan would produce on every single correct reply."""
    turns = [said("Usted tiene cita el jueves; si le viene bien, se la dejo así.")]

    assert words(turns, clinica.TU_FORMS) == []


def test_what_the_patient_says_is_never_the_agent_s_register() -> None:
    """Callers tutear all the time; only the agent's own turns are scored."""
    turns = [
        asked("oye, ¿me puedes cambiar tú la cita?"),
        said("Claro, ¿para qué día le viene bien?"),
    ]

    assert words(turns, clinica.TU_FORMS) == []


# --- the shop must never say usted ------------------------------------------


def test_a_shop_reply_in_tu_uses_no_forbidden_form() -> None:
    turns = [said("Tu pedido sale mañana y te llega el miércoles. ¿Te ayudo con algo más?")]

    assert words(turns, tienda.USTED_FORMS) == []


def test_a_shop_reply_that_slips_into_usted_is_caught() -> None:
    turns = [said("Disculpe, ¿me dice usted el número de pedido?")]

    assert sorted(words(turns, tienda.USTED_FORMS)) == ["disculpe", "usted"]


def test_the_shop_may_still_say_disculpa_and_espera_in_its_own_register() -> None:
    """The tú forms of the same verbs are not usted forms, and the scan tells them apart."""
    turns = [said("Disculpa la espera, espera un segundo que lo miro y te digo.")]

    assert words(turns, tienda.USTED_FORMS) == []
