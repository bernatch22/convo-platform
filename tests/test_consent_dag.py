"""The consent graph: two computed nodes, and what the graph costs in judge calls."""

import pytest
from deepeval.test_case import ConversationalTestCase

from convo.testing.metrics.dag import NOTHING_WAS_SAID, ran_at, said_before
from tests.fixtures.consent import (
    ASKED_AND_DECLINED,
    BOOK_APPOINTMENT,
    BOOK_SLOT,
    NOT_BOOKED,
    WAS_IT_A_YES,
    CountingJudge,
    agent,
    booked_after,
    metric_with,
)

pytestmark = pytest.mark.unit


# --- the two computed nodes -------------------------------------------------


def test_the_turn_a_tool_ran_in_is_read_off_the_transcript() -> None:
    turns = booked_after("sí, confirmo").turns

    assert ran_at(turns, BOOK_SLOT) == 5
    assert ran_at(turns, BOOK_APPOINTMENT) == 4


def test_a_tool_that_never_ran_has_no_turn() -> None:
    assert ran_at(NOT_BOOKED.turns, BOOK_SLOT) is None


def test_the_asking_tool_is_never_mistaken_for_the_write() -> None:
    """The confusion that made this node a judge call fail every correct call in ms-3."""
    assert ran_at(ASKED_AND_DECLINED.turns, BOOK_SLOT) is None
    assert ran_at(ASKED_AND_DECLINED.turns, BOOK_APPOINTMENT) == 2


def test_the_line_before_the_write_is_the_patient_s_own_words() -> None:
    turns = booked_after("sí, confirmo").turns

    assert said_before(turns, ran_at(turns, BOOK_SLOT)) == "sí, confirmo"


def test_the_agent_s_own_turns_are_never_the_consent_line() -> None:
    """The write and the confirmation are both assistant turns; the quote skips them both."""
    turns = booked_after("la de las once").turns

    assert said_before(turns, ran_at(turns, BOOK_SLOT)) == "la de las once"


def test_a_write_with_nobody_speaking_before_it_quotes_nothing() -> None:
    turns = [agent("le he cambiado la cita", BOOK_SLOT)]

    assert said_before(turns, 0) == ""


# --- what the graph costs ---------------------------------------------------


def test_a_call_that_booked_nothing_costs_no_judge_call_at_all() -> None:
    judge = CountingJudge()
    metric = metric_with(judge)

    assert metric.measure(NOT_BOOKED) == 1.0
    assert judge.prompts == []


def test_a_call_that_only_asked_for_confirmation_costs_no_judge_call_either() -> None:
    judge = CountingJudge()
    metric = metric_with(judge)

    assert metric.measure(ASKED_AND_DECLINED) == 1.0
    assert judge.prompts == []


def test_a_call_that_booked_costs_exactly_one_judge_call() -> None:
    judge = CountingJudge(verdict=True)
    metric = metric_with(judge)

    assert metric.measure(booked_after("sí, confirmo")) == 1.0
    assert len(judge.prompts) == 1


def test_the_one_judge_call_is_handed_the_line_and_not_the_call() -> None:
    """The node has no evaluation_params on purpose: given the transcript it scores the call."""
    judge = CountingJudge()
    metric_with(judge).measure(booked_after("sí, confirmo"))

    prompt = judge.prompts[0]
    assert "sí, confirmo" in prompt
    assert WAS_IT_A_YES in prompt
    assert "Clínica Norte" not in prompt


def test_a_booking_the_judge_calls_no_consent_is_a_zero_and_still_one_call() -> None:
    judge = CountingJudge(verdict=False)
    metric = metric_with(judge)

    assert metric.measure(booked_after("las once")) == 0.0
    assert len(judge.prompts) == 1


def test_a_write_nobody_was_asked_about_reaches_the_judge_as_a_stated_absence() -> None:
    judge = CountingJudge(verdict=False)
    case = ConversationalTestCase(turns=[agent("se la he cambiado ya", BOOK_SLOT)])

    assert metric_with(judge).measure(case) == 0.0
    assert NOTHING_WAS_SAID in judge.prompts[0]


def test_every_node_writes_its_own_line_into_the_log_a_reviewer_reads() -> None:
    """`include_reason=False` leaves no generated summary, so the chain has to say it all."""
    judge = CountingJudge()
    metric = metric_with(judge)
    metric.measure(ASKED_AND_DECLINED)

    assert BOOK_SLOT in metric.verbose_logs
    assert BOOK_APPOINTMENT in metric.verbose_logs
