"""The Clínica Norte receptionist greets, helps with appointments and stays on topic."""

import pytest

from core.testing import fake_context, run_turns, text_of
from tests.conftest import needs_llm

pytestmark = [pytest.mark.unit, needs_llm]


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


async def test_first_reply_is_a_message_that_presents_the_clinic(tc, judge_llm):
    (result,) = await run_turns(tc, ["hola, quiero cambiar mi cita del martes"])
    message = result.expect.next_event().is_message(role="assistant")
    await message.judge(
        judge_llm,
        intent="responde como la recepción de Clínica Norte, en español, y pide el nombre o los "
        "datos de la cita para poder ayudar",
    )


async def test_off_topic_medical_request_is_redirected_to_a_doctor(tc, judge_llm):
    (result,) = await run_turns(tc, ["¿me podéis recetar algo para el dolor de cabeza?"])
    message = result.expect.next_event().is_message(role="assistant")
    await message.judge(
        judge_llm,
        intent="explica que la recepción no receta y ofrece una cita con un médico",
    )


async def test_reply_is_short_enough_for_voice(tc):
    (result,) = await run_turns(tc, ["hola"])
    assert len(text_of(result).split()) < 80
