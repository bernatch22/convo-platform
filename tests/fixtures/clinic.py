"""Fixtures and fakes shared by the clinic tests."""

import importlib
import inspect
from types import SimpleNamespace

import pytest

from convo.testing import fake_context

PROJECT = "tenants.clinica-norte.projects.reagendamiento"
project_module = importlib.import_module(f"{PROJECT}.project")
stages = importlib.import_module(f"{PROJECT}.stages")
choose_slot = importlib.import_module(f"{PROJECT}.stages.choose_slot")
new_booking = importlib.import_module(f"{PROJECT}.stages.new_booking")
update_contact = importlib.import_module(f"{PROJECT}.stages.update_contact")
cancel_or_confirm = importlib.import_module(f"{PROJECT}.stages.cancel_or_confirm")
identify = importlib.import_module(f"{PROJECT}.stages.identify")
helpers_module = importlib.import_module(f"{PROJECT}.helpers")
messages_module = importlib.import_module(f"{PROJECT}.messages")
patients = importlib.import_module("tenants.clinica-norte.adapters.patients")

ANA = "ap-20260903-1000-trau"  # the seeded appointment every test reschedules
THURSDAY_11 = {"id": "sl-20260903-1100-trau", "when": "2026-09-03T11:00", "doctor": "Dra. Ruiz"}
REFUSED_13 = {"id": "sl-20260908-1300-trau", "when": "2026-09-08T13:00", "doctor": "Dra. Campos"}
PEDRO = {"patient": "Pedro Ramos Gil", "phone": "699000000"}  # nobody the book has ever held
NEW_NUMBER = "689000111"  # what Ana moves to; the 600-block one she leaves is 600123456


@pytest.fixture
def tc():
    """A session that has already identified Ana García, which is where ChooseSlot begins."""
    return identified_context()


def identified_context():
    """A context past the Identify stage: the patient is found and her cita is known.

    `prev_agent` matters as much as `customer`: what ChooseSlot knows about the
    caller arrives as the previous stage's `summary()` in its `on_enter`, and a
    stage entered without one asks for the name again — which is the right
    behaviour and the wrong test. Shared with `tests/test_reception_tools.py`,
    which reads the agenda from this same stage.
    """
    context = fake_context("clinica-norte", "reagendamiento")
    context.customer = {"appointment_id": ANA, **context.adapters["agenda"].book[ANA]}
    context.prev_agent = stages.Identify(context)
    return context


@pytest.fixture
def unknown():
    """A session past Identify for somebody with NO cita: exactly where NewBooking begins.

    `customer` carries a name and a phone and no `appointment_id` — which is the
    whole difference between the two booking stages, and the thing `Identify`
    writes when the caller asks for a first appointment.
    """
    context = fake_context("clinica-norte", "reagendamiento")
    context.customer = dict(PEDRO)
    context.prev_agent = stages.Identify(context)
    return context


def booking(tc) -> stages.NewBooking:
    """The NewBooking stage entered the way a real call enters it: after an identification."""
    return stages.NewBooking(tc)


def new_booking_args(tc, slot: dict[str, str], specialty: str = "traumatología") -> dict[str, str]:
    return new_booking._booking_args(tc, slot, specialty)


@pytest.fixture
def settling(tc):
    """A session that reached CancelOrConfirm: Ana identified, the errand a cancellation.

    `Identify.errand` again, and again it is not decoration: it is what makes the
    note this stage inherits tell it to look the cita up instead of reciting one,
    which is the rule the whole stage is built on.
    """
    tc.prev_agent.errand = identify.CANCEL
    return stages.CancelOrConfirm(tc)


@pytest.fixture
def changing(tc):
    """A session that reached UpdateContact: Ana identified, and the errand a data change.

    `Identify.errand` is not decoration. It is what makes the summary this stage
    inherits carry the phone number masked, which is the safeguard the errand is
    built on — so a fixture that skipped it would be testing a stage no call can
    produce.
    """
    tc.prev_agent.errand = identify.CONTACT
    return stages.UpdateContact(tc)


def contact_args(tc, phone: str = NEW_NUMBER) -> dict[str, str]:
    return update_contact._contact_args(tc, phone)


def _arguments(tool) -> list[str]:
    """The parameters a stage tool exposes to the model, ctx aside — its whole reach."""
    signature = inspect.signature(getattr(tool, "__func__", tool))
    return [name for name in signature.parameters if name not in ("self", "ctx")]


def run_context(tc):
    """The one thing a stage tool reads off its RunContext, and nothing else.

    A real `RunContext` belongs to a running session; these tests call the tool
    directly because what they pin is the refusal, which happens before any model
    is involved. `userdata` is the whole of the contract they need.
    """
    return SimpleNamespace(userdata=tc)


def choosing(tc) -> stages.ChooseSlot:
    """The ChooseSlot stage entered the way a real call enters it: after an identification."""
    return stages.ChooseSlot(tc)


def booking_args(tc, slot: dict[str, str]) -> dict[str, str]:
    return choose_slot._booking_args(tc, slot)
