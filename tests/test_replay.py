"""Replay: an append-only log read back as the case a conversational metric scores.

Every event here is written by hand. A conversion pinned through a live call
would be a test of the call — of Haiku's mood, of the agenda's seed data — and
would say nothing about the one thing this module owns: which turn a tool hangs
from, and what a judge is told about a result the log never stored.
"""

import pytest

from convo.state.events import Event
from convo.state.store import MemoryStore, SessionRow
from convo.testing.replay import (
    NO_PAYLOAD,
    conversational_case_from,
    missing_tool_outputs,
    turns_from,
)

pytestmark = pytest.mark.unit

DESCRIPTIONS = {
    "find_availability": "Consulta la agenda y devuelve hasta tres huecos libres de un día.",
    "book_slot": "Mueve la cita del paciente a la hora que ha confirmado.",
}

# What the clinic's `find_availability` renders into `tool.result` (its ToolSpec declares a
# `result_summary`); `book_slot` deliberately declares none, so one call in this log is
# evidence and the other is a shape — which is the pair every assertion below needs.
AGENDA_SAID = "3 free slots: 2026-09-03T10:00 Dra. Gómez; 2026-09-03T12:30 Dr. Molina"

# One booking as the observers and the executor really write it: a filler line before the
# agenda is consulted, and the three writes landing after the caller's yes, while the agent
# is already saying goodbye.
BOOKING = [
    ("session.start", {"tenant": "clinica-norte", "project": "reagendamiento"}),
    ("stage.enter", {"stage": "ChooseSlot"}),
    ("turn.agent", {"text": "Clínica Norte, ¿en qué puedo ayudarle?"}),
    ("turn.user", {"text": "¿qué huecos hay el jueves?"}),
    ("turn.agent", {"text": "Un momento, le consulto la agenda."}),
    ("tool.call", {"tool": "find_availability", "args": {"date": "2026-09-03"}}),
    ("tool.result", {"tool": "find_availability", "shape": "list[3]", "summary": AGENDA_SAID}),
    ("turn.agent", {"text": "El jueves tengo las diez de la mañana con la Dra. Gómez."}),
    ("turn.user", {"text": "la primera que me ha dicho"}),
    ("confirm.request", {"tool": "book_slot", "audience": "el jueves a las diez"}),
    ("turn.agent", {"text": "¿Le confirmo el jueves a las diez de la mañana?"}),
    ("turn.user", {"text": "sí, confirmo"}),
    ("confirm.granted", {"tool": "book_slot", "audience": "el jueves a las diez"}),
    ("tool.call", {"tool": "book_slot", "args": {"slot_id": "s-1", "phone": "***"}}),
    ("tool.result", {"tool": "book_slot", "shape": "dict[4]"}),
    ("stage.handoff", {"from": "ChooseSlot", "to": "Farewell"}),
    ("turn.agent", {"text": "Queda cambiada. Que vaya muy bien."}),
    ("session.end", {"outcome": "completed"}),
]


def events(pairs: list[tuple[str, dict]]) -> list[Event]:
    """A hand-written log, numbered as the EventLog would number it."""
    return [
        Event(seq=index, kind=kind, t_ms=index * 100, payload=payload)
        for index, (kind, payload) in enumerate(pairs, start=1)
    ]


def test_only_the_turns_become_turns_and_they_keep_their_order() -> None:
    turns = turns_from(events(BOOKING), DESCRIPTIONS)

    assert [turn.role for turn in turns] == [
        "assistant",  # the greeting, before anybody said anything
        "user",
        "assistant",  # "un momento, le consulto la agenda"
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert turns[1].content == "¿qué huecos hay el jueves?"
    assert turns[-1].content == "Queda cambiada. Que vaya muy bien."


def test_a_tool_hangs_from_the_turn_that_answered_with_it_not_the_filler_before_it() -> None:
    turns = turns_from(events(BOOKING), DESCRIPTIONS)

    assert turns[2].tools_called is None  # "un momento" ran nothing; the agenda came after
    called = turns[3].tools_called
    assert [call.name for call in called] == ["find_availability"]
    assert called[0].input_parameters == {"date": "2026-09-03"}
    assert called[0].description == DESCRIPTIONS["find_availability"]


def test_the_irreversible_write_lands_on_the_farewell_turn_it_happened_before() -> None:
    turns = turns_from(events(BOOKING), DESCRIPTIONS)

    assert [call.name for call in turns[-1].tools_called] == ["book_slot"]
    # what the metric needs: the last user turn before that assistant turn is the yes
    assert turns[-2].content == "sí, confirmo"


def test_a_declared_summary_is_what_the_judge_reads_as_the_output_of_the_call() -> None:
    """The ms-7 field: an hour the agenda offered is evidence, not a shape and an apology."""
    turns = turns_from(events(BOOKING), DESCRIPTIONS)

    assert turns[3].tools_called[0].output == AGENDA_SAID


def test_a_result_with_no_summary_carries_its_shape_and_says_the_payload_was_never_stored() -> None:
    turns = turns_from(events(BOOKING), DESCRIPTIONS)

    output = turns[-1].tools_called[0].output
    assert output.startswith("dict[4]")
    assert NO_PAYLOAD in output


def test_the_arguments_are_the_masked_ones_the_executor_wrote_nothing_is_re_masked() -> None:
    turns = turns_from(events(BOOKING), DESCRIPTIONS)

    assert turns[-1].tools_called[0].input_parameters == {"slot_id": "s-1", "phone": "***"}


def test_a_refused_call_is_still_a_call_and_says_nothing_was_written() -> None:
    log = [
        ("turn.user", {"text": "cámbiamela sin más"}),
        ("tool.refused", {"tool": "book_slot", "args": {}, "reason": "no confirmation token"}),
        ("turn.agent", {"text": "Antes tengo que confirmárselo."}),
    ]

    call = turns_from(events(log))[-1].tools_called[0]

    assert call.name == "book_slot"
    assert "refused" in call.output and "nothing was written" in call.output


def test_a_call_the_process_never_answered_keeps_no_output_and_is_not_lost() -> None:
    """A SIGKILL between `tool.call` and `tool.result` — the log ends where the call did."""
    log = [
        ("turn.user", {"text": "el jueves"}),
        ("turn.agent", {"text": "Un momento."}),
        ("tool.call", {"tool": "find_availability", "args": {"date": "2026-09-03"}}),
    ]

    call = turns_from(events(log))[-1].tools_called[0]

    assert call.name == "find_availability"
    assert call.output is None


def test_a_failed_call_says_so_instead_of_pretending_it_returned_something() -> None:
    log = [
        ("tool.call", {"tool": "find_availability", "args": {}}),
        ("tool.error", {"tool": "find_availability", "key": "timeout"}),
        ("turn.agent", {"text": "La agenda no me responde."}),
    ]

    assert "failed" in turns_from(events(log))[-1].tools_called[0].output


def test_missing_tool_outputs_names_only_the_tools_that_declared_no_summary() -> None:
    case = conversational_case_from(stored(BOOKING), "sess-1", DESCRIPTIONS)

    assert missing_tool_outputs(case) == ["book_slot"]


def test_a_case_is_named_after_the_session_and_says_where_it_came_from() -> None:
    case = conversational_case_from(stored(BOOKING), "sess-1")

    assert case.name == "sess-1"
    assert "clinica-norte/reagendamiento" in case.scenario
    assert case.expected_outcome is None  # a real call is not a golden


def test_a_session_that_is_not_in_the_store_is_a_lookup_error_not_an_empty_case() -> None:
    with pytest.raises(LookupError):
        conversational_case_from(MemoryStore(), "nobody")


def stored(pairs: list[tuple[str, dict]]) -> MemoryStore:
    """A MemoryStore holding one session with these events."""
    store = MemoryStore()
    store.open_session(
        SessionRow(
            id="sess-1",
            tenant="clinica-norte",
            project="reagendamiento",
            channel="chat",
            started_at=0.0,
        )
    )
    for event in events(pairs):
        store.append("sess-1", event)
    return store
