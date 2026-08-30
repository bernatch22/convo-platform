"""The Clínica Norte receptionist greets, helps with appointments and stays on topic."""

import pytest

from core.testing import fake_context, final_message, run_turns, text_of
from tests.conftest import needs_llm

pytestmark = [pytest.mark.unit, needs_llm]


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


async def test_the_reply_moves_the_reschedule_forward(tc, judge_llm):
    """Judged on what this turn owes the caller, not on re-introducing the clinic.

    `run_turns` drops the greeting, so the message under test is a mid-conversation
    reply: the agent has already said who it is and does not repeat it, which is
    right on a phone call. Asking it to present the clinic again made this golden
    a coin flip (3 failures in 6 runs) on a reply that was perfectly good.

    The list of steps is spelled out as "any ONE of these is enough". Written as
    a plain "a, b or c" the judge read it as a checklist and failed "¿para qué
    día le vendría bien?" for not also asking the name — the same standard, and
    the same reply, scored both ways depending on how the sentence parsed.
    """
    (result,) = await run_turns(tc, ["hola, quiero cambiar mi cita del martes"])
    message = final_message(result)
    await message.judge(
        judge_llm,
        intent="responde en español, como la recepción de una clínica, y da UN paso concreto "
        "hacia el cambio de cita. Basta con uno cualquiera de estos cuatro, y no hacen falta "
        "los demás: preguntar qué día prefiere; ofrecer horas libres; pedir el nombre del "
        "paciente; pedir los datos de la cita actual",
    )


async def test_off_topic_medical_request_is_redirected_to_a_doctor(tc, judge_llm):
    (result,) = await run_turns(tc, ["¿me podéis recetar algo para el dolor de cabeza?"])
    message = final_message(result)
    await message.judge(
        judge_llm,
        intent="explica que la recepción no receta y ofrece una cita con un médico",
    )


async def test_reply_is_short_enough_for_voice(tc):
    (result,) = await run_turns(tc, ["hola"])
    assert len(text_of(result).split()) < 80
