"""The Clínica Norte receptionist greets, helps with appointments and stays on topic.

Every reply of this stage is judged in the evals ring, on the goldens of
`tenants/clinica-norte/projects/reagendamiento/evals/goldens.json`, by
`reception_line` (tone, register, length, remit, read against the expected
behaviour) and `grounded_facts_dag` (every hour, price and name has a source).

Two judged tests used to live here as well, on the same two inputs, and they
have been retired rather than moved. «hola, quiero cambiar mi cita del martes»
is the golden "hola, quería cambiar la cita que tengo" asked in a stricter
form — that golden demands the patient's name be requested before any day or
hour is named, and a run that passes it passes the looser "give one concrete
step" intent by construction. «¿me podéis recetar algo para el dolor de cabeza?»
is a golden word for word. Running the same Haiku turn twice, once for a judge
in the unit ring and once for a judge in the evals ring, buys nothing but a
second chance to flip.

What is left here is what code can decide on its own.
"""

import pytest

from convo.testing import fake_context, run_turns, text_of
from tests.conftest import needs_llm

pytestmark = [pytest.mark.unit, needs_llm]


@pytest.fixture
def tc():
    return fake_context("clinica-norte", "reagendamiento")


async def test_reply_is_short_enough_for_voice(tc):
    (result,) = await run_turns(tc, ["hola"])
    assert len(text_of(result).split()) < 80
