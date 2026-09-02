"""Masking by VALUE: a name the contract never named still has to leave the log.

`pii_scope` masks an argument by name, which is the right primitive and only
half the job: `send_sms` declares `pii_scope={"phone"}` and puts the patient's
name in the middle of `text`. So the executor remembers the values it has seen
declared as PII (`tc.pii_values`) and the mask blanks them wherever they turn
up again — in an SMS body, in a confirmation question, in a refusal.

Still no global regex: a string is PII here only because some `ToolSpec`, on
some call, said that argument was. No model and no network in this file.
"""

import importlib

import pytest

from convo.domain.tools import SideEffect, ToolSpec
from convo.state.log import record
from convo.testing.harness import fake_context
from convo.tools import confirm, guard
from convo.tools.guard import ToolRefused, mask

pytestmark = pytest.mark.unit

APPOINTMENT = "ap-20260903-1000-trau"  # seeded in tenants/clinica-norte/adapters/patients.py
PATIENT = "Ana García Ruiz"
MASKED_PATIENT = "An*************"
PHONE = "600123456"
MASKED_PHONE = "60*******"
SLOT = {"id": "s-11", "when": "2026-09-03T11:00", "doctor": "Dra. Irene Campos"}
BOOKABLE = "sl-20260903-0900-trau"  # a real slot id: `book_slot` reads the moment out of it

project_tools = importlib.import_module("tenants.clinica-norte.projects.reagendamiento.helpers")


def clinic_context(identified: bool = True):
    """A Clínica Norte session with a real catalog, real adapters and an in-memory log."""
    tc = fake_context("clinica-norte", "reagendamiento")
    if identified:
        tc.customer = {"appointment_id": APPOINTMENT, **tc.adapters["agenda"].book[APPOINTMENT]}
    return tc


def payload(tc, kind: str) -> dict:
    return next(event.payload for event in tc.log.events() if event.kind == kind)


def sms_args(tc) -> dict:
    return payload(tc, "tool.call")["args"]


# ── the leak this card was opened for ────────────────────────────────────────


async def test_the_patient_name_inside_the_sms_body_never_reaches_the_log() -> None:
    """seq 31 of the observers' booking run: `text` carried 'Ana García Ruiz' in the clear."""
    tc = clinic_context()
    text = project_tools.sms_text(PATIENT, SLOT)

    await tc.tools.call("send_sms", {"phone": PHONE, "text": text})

    logged = sms_args(tc)
    assert logged["text"].startswith(f"Clínica Norte: {MASKED_PATIENT}, su cita")
    assert logged["phone"] == MASKED_PHONE
    assert PATIENT not in str(logged) and PHONE not in str(logged)


async def test_the_gateway_still_sends_the_real_name_and_the_real_number() -> None:
    """Masking is a property of the log copy; the patient must receive a readable SMS."""
    tc = clinic_context()
    text = project_tools.sms_text(PATIENT, SLOT)

    await tc.tools.call("send_sms", {"phone": PHONE, "text": text})

    sent = tc.adapters["sms"].sent[0]
    assert sent["text"] == text and sent["to"] == PHONE
    assert tc.adapters["sms"].calls[0][1] == {"phone": PHONE, "text": text}


async def test_a_text_that_names_nobody_is_logged_word_for_word() -> None:
    tc = clinic_context()
    plain = "Clínica Norte: su cita queda confirmada. Para cambiarla llame al 910 000 000."

    await tc.tools.call("send_sms", {"phone": PHONE, "text": plain})

    assert sms_args(tc)["text"] == plain


async def test_a_value_first_seen_in_this_call_is_masked_in_this_calls_own_line() -> None:
    """Learning after masking would leak the first occurrence — the one that matters."""
    tc = clinic_context(identified=False)

    await tc.tools.call(
        "send_sms", {"phone": PHONE, "text": f"Le devolvemos la llamada al {PHONE}."}
    )

    assert sms_args(tc)["text"] == f"Le devolvemos la llamada al {MASKED_PHONE}."


async def test_a_refused_irreversible_call_names_nobody_in_the_line_it_leaves() -> None:
    tc = clinic_context()
    args = {"slot_id": SLOT["id"], "patient": PATIENT, "phone": PHONE, "doctor": SLOT["doctor"]}

    with pytest.raises(ToolRefused):
        await tc.tools.call("book_slot", args)  # no confirmation token: the guard vetoes it

    line = str(payload(tc, "tool.refused"))
    assert PATIENT not in line and PHONE not in line
    assert "book_slot" in line


# ── the summaries: what a result is allowed to say about itself (ms-7) ───────


async def test_the_summary_of_a_lookup_names_the_appointment_and_never_the_patient() -> None:
    """`find_patient` is asked for a phone and answers with a name nothing had declared yet."""
    tc = clinic_context(identified=False)

    await tc.tools.call("find_patient", {"phone": PHONE})

    summary = payload(tc, "tool.result")["summary"]
    assert MASKED_PATIENT in summary, summary
    assert PATIENT not in summary and PHONE not in summary
    assert "2026-09-03T10:00" in summary and "Dra. Irene Campos" in summary


async def test_no_summary_of_a_whole_rebooking_carries_a_name_or_a_number() -> None:
    """The card's acceptance, asserted over every result line a real rebooking writes."""
    tc = clinic_context(identified=False)
    booking = {"slot_id": BOOKABLE, "patient": PATIENT, "phone": PHONE, "doctor": SLOT["doctor"]}

    await tc.tools.call("find_patient", {"phone": PHONE})
    await tc.tools.call("find_availability", {"date": "2026-09-03"})
    await tc.tools.call("cancel_slot", {"appointment_id": APPOINTMENT})
    confirm.mint(tc, "book_slot", booking)
    await tc.tools.call("book_slot", booking)
    await tc.tools.call("send_sms", {"phone": PHONE, "text": project_tools.sms_text(PATIENT, SLOT)})

    summaries = [
        event.payload["summary"] for event in tc.log.events() if "summary" in event.payload
    ]
    assert len(summaries) == 5, summaries
    for summary in summaries:
        assert PATIENT not in summary and PHONE not in summary, summary


# ── the seams: free text no ToolSpec describes ───────────────────────────────


def test_a_seam_that_logs_free_text_is_scrubbed_by_the_same_known_values() -> None:
    """A confirmation question may name the doctor; it must never name the patient."""
    tc = clinic_context()
    tc.pii_values = {PATIENT}

    record(tc, "confirm.request", {"tool": "book_slot", "question": f"{PATIENT}, ¿lo confirmo?"})

    assert payload(tc, "confirm.request")["question"] == f"{MASKED_PATIENT}, ¿lo confirmo?"


def test_scrub_reaches_a_value_nested_inside_a_payload() -> None:
    scrubbed = guard.scrub({"step": "send_sms", "args": {"text": [PATIENT]}}, {PATIENT})

    assert scrubbed == {"step": "send_sms", "args": {"text": [MASKED_PATIENT]}}


# ── the rules of the mask itself ─────────────────────────────────────────────


def test_a_value_of_two_characters_is_never_used_as_a_pattern() -> None:
    """Blanking every '53' in a log destroys the line and protects nobody."""
    spec = ToolSpec(name="pick", side_effect=SideEffect.WRITE, pii_scope=frozenset({"code"}))

    masked = mask(spec, {"code": "53", "note": "hay 53 huecos"}, known={"53", "3"})

    assert masked == {"code": "**", "note": "hay 53 huecos"}


def test_learn_keeps_only_the_values_worth_masking_by() -> None:
    known: set[str] = set()

    guard.learn(known, [PATIENT, "60", None, "   ", PHONE])

    assert known == {PATIENT, PHONE}


def test_a_full_name_is_masked_before_the_first_name_it_contains() -> None:
    """Longest pattern first, or 'Ana' would eat its own surname's mask."""
    spec = ToolSpec(name="notify", side_effect=SideEffect.WRITE)

    masked = mask(spec, {"text": f"para {PATIENT}"}, known={"Ana", PATIENT})

    assert masked == {"text": f"para {MASKED_PATIENT}"}


def test_a_non_string_argument_is_left_exactly_as_it_was() -> None:
    spec = ToolSpec(name="notify", side_effect=SideEffect.WRITE)

    masked = mask(spec, {"count": 3, "ok": True}, known={PATIENT})

    assert masked == {"count": 3, "ok": True}
