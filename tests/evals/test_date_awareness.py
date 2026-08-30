"""Asked what day it is, the agent reads the note instead of inventing a weekday.

The defect this pins was found on a real call: the agent answered "Hoy es
viernes" on a Saturday. The note is written once per session; the clock is a
tool. This is the judged half — it belongs to the evals ring, never to unit
(`tests/test_date_note.py` holds the LLM-free half).
"""

import pytest

from core.testing import fake_context, final_message, run_conversation

pytestmark = pytest.mark.evals


async def test_asked_what_day_it_is_the_agent_answers_the_real_one(judge_llm) -> None:
    tc = fake_context("clinica-norte", "reagendamiento")  # today frozen: Tuesday 2026-09-01
    conversation = await run_conversation(tc, ["hola, ¿qué día es hoy?"])

    await final_message(conversation.results[0]).judge(
        judge_llm,
        intent="Dice que hoy es martes (1 de septiembre de 2026), sin inventar otro día.",
    )
