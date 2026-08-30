"""What the shop's agent claimed and what the call could back it up with — the free half.

The clinic's version of this suite is `tests/test_grounding.py`; the machinery
under both is `core.testing.grounding` and what differs is one tuple of
extractors. These are the three things a customer would act on and an agent
could invent — an order number, a tracking code, a carrier — plus the prices,
hours and phones every project gets from core.

Fake turns rather than real ones: a conversation with Haiku costs seconds and
moves between runs, and none of that is needed to prove that «TS-10432» is in
the evidence and «TS-99999» is not.
"""

import importlib
from dataclasses import dataclass, field

import pytest
from deepeval.test_case import ToolCall

pytestmark = pytest.mark.unit

grounding = importlib.import_module("tenants.tienda-sur.projects.pedidos.evals.grounding")


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


def found(order: str) -> ToolCall:
    """The order row as `find_order` hands it back, which is what grounds a reply about it."""
    return ToolCall(name="find_order", output=order)


# --- what counts as a checkable fact ----------------------------------------


def test_a_reply_that_states_no_number_and_no_code_states_nothing_to_check() -> None:
    """A policy is not a fact: «se puede cancelar» has nobody to be wrong about."""
    assert kinds([said("Claro, mientras esté preparándose se puede cancelar sin problema.")]) == []


def test_order_numbers_tracking_codes_carriers_prices_and_phones_are_what_gets_checked() -> None:
    turns = [
        said(
            "Tu pedido TS-10432 sale con Correos Express, seguimiento CE884512377ES; el envío "
            "son 3,95 euros y nos llamas al 954 000 000."
        )
    ]

    assert set(kinds(turns)) == {"pedido", "seguimiento", "transportista", "precio", "teléfono"}


def test_an_order_number_is_one_fact_however_the_agent_spaces_it() -> None:
    turns = [said("El TS-10432, sí, el pedido TS 10432.")]

    assert kinds(turns) == ["pedido"]


# --- what grounds it --------------------------------------------------------


def test_a_return_window_from_the_shop_s_own_sheet_needs_no_tool_behind_it() -> None:
    """The answer a judge with no evidence in front of it used to call an invention."""
    turns = [asked("¿cuánto cuesta el envío?"), said("El estándar son 3,95 euros.")]

    assert leftover(turns) == []


def test_a_shipping_price_that_is_on_no_sheet_is_left_over_for_the_judge() -> None:
    assert leftover([said("El envío te sale por 18 euros.")]) == ["18 euros"]


def test_an_order_number_the_customer_read_out_is_grounded_by_the_customer() -> None:
    """The caller is a source: repeating back what they just said is not an invention."""
    turns = [asked("es el pedido TS 10432"), said("Perfecto, el TS-10432 lo tengo aquí.")]

    assert leftover(turns) == []


def test_a_tracking_code_the_order_system_returned_is_grounded_by_the_tool_output() -> None:
    turns = [
        said(
            "Ya ha salido, con Correos Express y seguimiento CE884512377ES.",
            [found("Pedido TS-10433. Enviado. Seguimiento: CE884512377ES, Correos Express.")],
        )
    ]

    assert leftover(turns) == []


def test_a_tracking_code_nobody_returned_is_left_over() -> None:
    row = found("Pedido TS-10432. Sin seguimiento.")
    turns = [said("Tu seguimiento es el CE111111111ES.", [row])]

    assert leftover(turns) == ["CE111111111ES"]


def test_a_carrier_the_shop_never_gave_the_parcel_to_is_left_over() -> None:
    """MRW is a real carrier of ours; it is still an invention on a parcel SEUR is carrying."""
    turns = [said("Lo lleva MRW.", [found("Pedido TS-10434. Transportista: SEUR.")])]

    assert leftover(turns) == ["MRW"]


def test_the_agent_s_own_earlier_reply_is_never_evidence_for_its_later_one() -> None:
    """Otherwise an invention launders itself one turn later by being repeated."""
    turns = [said("Es el pedido TS-99999."), asked("¿cómo dices?"), said("El TS-99999.")]

    assert leftover(turns) == ["TS-99999"]
