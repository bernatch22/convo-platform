"""Cross-tenant leakage: the half of the metric that is a word list, with no judge in it.

One worker serves both businesses, so "the shop never answers as the clinic" is
a claim about `core/` — and the cheapest half of checking it is deterministic:
did the reply name anything that belongs only to the other tenant? These rules
run in microseconds and are what makes the metric worth running on every build.

The interesting half is the false positives. A scan that matched substrings, or
a word list with bare surnames in it, would fail correct calls: Tienda Sur has a
customer called Marta Alonso **Gil** and Clínica Norte has a **Dr. Ramón Gil**.
"""

import importlib
from dataclasses import dataclass

import pytest

from core.testing.leakage import mentions

pytestmark = pytest.mark.unit

clinica = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.evals.dag")
tienda = importlib.import_module("tenants.tienda-sur.projects.pedidos.evals.dag")


@dataclass
class FakeTurn:
    """Enough of a deepeval Turn for the scan: who spoke, and what they said."""

    role: str
    content: str


def test_the_shop_naming_the_clinic_is_caught_however_it_is_written() -> None:
    turns = [FakeTurn("assistant", "Eso se lo miran en Clinica Norte, con el dr alberto navarro.")]

    found = mentions(turns, tienda.CLINIC_TERMS)

    assert [term for _, term in found] == ["clinica norte", "dr alberto navarro"]


def test_a_correct_shop_reply_about_a_doctor_it_cannot_book_is_not_a_leak() -> None:
    turns = [FakeTurn("assistant", "Aquí solo vendemos ropa, no damos citas de traumatología.")]

    assert mentions(turns, tienda.CLINIC_TERMS) == []


def test_the_clinic_naming_the_shop_or_its_carriers_is_caught() -> None:
    turns = [FakeTurn("assistant", "Su paquete lo lleva SEUR; pregunte en Tienda Sur.")]

    found = mentions(turns, clinica.SHOP_TERMS)

    assert [term for _, term in found] == ["tienda sur", "seur"]


def test_what_the_caller_says_is_never_a_leak() -> None:
    turns = [FakeTurn("user", "vengo de Tienda Sur y me han dicho que os llame")]

    assert mentions(turns, clinica.SHOP_TERMS) == []
