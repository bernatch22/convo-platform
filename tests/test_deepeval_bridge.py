"""The RunResult → LLMTestCase bridge, with no model anywhere near it.

`tool_calls_of` and `test_case_for` are the seam every eval suite from ms-3 on
will sit behind, so they are pinned by fake turns rather than by real ones: a
conversation with Haiku costs seconds and moves between runs, and none of that
is needed to prove that a function_call event becomes a ToolCall with its
arguments parsed. The fakes below carry exactly the two attributes the bridge
reads (`type` and `item`), which is also a statement of how little of LiveKit's
RunResult it is allowed to depend on.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
from deepeval.metrics import ToolCorrectnessMetric

from convo.testing.harness import Conversation, Exchange, PlatformCall, fake_context
from convo.testing.metrics import deepeval as bridge

pytestmark = pytest.mark.unit


@dataclass
class FakeMessage:
    """A `message` event's item: what the assistant said in one chunk of a turn."""

    text_content: str
    role: str = "assistant"


@dataclass
class FakeCall:
    """A `function_call` event's item: the tool name and the raw JSON the model produced."""

    name: str
    arguments: str
    call_id: str = "call-1"


@dataclass
class FakeOutput:
    """A `function_call_output` event's item: what the tool handed back, keyed by call."""

    output: str
    call_id: str = "call-1"


@dataclass
class FakeEvent:
    type: str
    item: Any


@dataclass
class FakeResult:
    """Enough of a RunResult for the bridge: an ordered list of events."""

    events: list[FakeEvent] = field(default_factory=list)


def message(text: str, role: str = "assistant") -> FakeEvent:
    return FakeEvent(type="message", item=FakeMessage(text_content=text, role=role))


def call(name: str, arguments: str, call_id: str = "call-1") -> FakeEvent:
    item = FakeCall(name=name, arguments=arguments, call_id=call_id)
    return FakeEvent(type="function_call", item=item)


def output(text: str, call_id: str = "call-1") -> FakeEvent:
    item = FakeOutput(output=text, call_id=call_id)
    return FakeEvent(type="function_call_output", item=item)


def conversation_of(greeting: str, *results: FakeResult, said: str = "hola") -> Conversation:
    """A run of one turn per result, all answering the same line."""
    exchanges = [Exchange(input=said, result=result) for result in results]
    return Conversation(greeting=greeting, exchanges=exchanges)


GOLDEN = {
    "input": "¿qué turnos hay el jueves?",
    "expected_behaviour": "Consulta la agenda del jueves y ofrece horas.",
    "expected_tools": ["find_availability"],
}
GREETING_GOLDEN = {
    "input": "(llamada entrante)",
    "turn": "greeting",
    "expected_behaviour": "Saluda y se presenta.",
    "expected_tools": [],
}


# --- tool_calls_of ----------------------------------------------------------


def test_a_function_call_event_becomes_a_tool_call_with_its_arguments_parsed() -> None:
    result = FakeResult([call("find_availability", '{"date": "el jueves", "specialty": null}')])

    calls = bridge.tool_calls_of(result)

    assert len(calls) == 1
    assert calls[0].name == "find_availability"
    assert calls[0].input_parameters == {"date": "el jueves", "specialty": None}


def test_the_arguments_are_kept_as_the_model_wrote_them() -> None:
    """ "el jueves" is what the model chose; the date it resolves to is the tool's business."""
    result = FakeResult([call("find_availability", '{"date": "el jueves"}')])

    assert bridge.tool_calls_of(result)[0].input_parameters["date"] == "el jueves"


def test_several_calls_in_one_turn_keep_the_order_the_model_made_them_in() -> None:
    result = FakeResult(
        [
            call("find_availability", '{"date": "el jueves"}'),
            message("Un momento, le miro traumatología."),
            call("find_availability", '{"date": "el jueves", "specialty": "traumatología"}'),
        ]
    )

    assert [c.input_parameters.get("specialty") for c in bridge.tool_calls_of(result)] == [
        None,
        "traumatología",
    ]


def test_a_turn_that_only_talked_called_nothing() -> None:
    assert bridge.tool_calls_of(FakeResult([message("Le atiendo enseguida.")])) == []


def test_arguments_that_are_not_a_json_object_are_kept_instead_of_raising() -> None:
    """An eval exists to show a malformed call, not to die on it."""
    assert bridge.tool_calls_of(FakeResult([call("find_availability", "{oops")]))[
        0
    ].input_parameters == {"_raw": "{oops"}
    assert (
        bridge.tool_calls_of(FakeResult([call("find_availability", "")]))[0].input_parameters == {}
    )


def test_a_call_carries_what_the_tool_returned_so_a_judge_can_see_the_evidence() -> None:
    """Without the output, a judge cannot tell an hour read off the agenda from an invented one."""
    result = FakeResult(
        [
            call("find_availability", '{"date": "el jueves"}', call_id="c1"),
            output("Huecos libres el jueves 3: 11:00 Dra. Ruiz", call_id="c1"),
        ]
    )

    assert bridge.tool_calls_of(result)[0].output == "Huecos libres el jueves 3: 11:00 Dra. Ruiz"


def test_each_call_gets_its_own_output_and_never_the_other_one_s() -> None:
    result = FakeResult(
        [
            call("find_availability", '{"date": "el jueves"}', call_id="c1"),
            output("sin especialidad", call_id="c1"),
            call("find_availability", '{"date": "el jueves", "specialty": "x"}', call_id="c2"),
            output("con especialidad", call_id="c2"),
        ]
    )

    assert [c.output for c in bridge.tool_calls_of(result)] == [
        "sin especialidad",
        "con especialidad",
    ]


def test_a_call_is_described_to_the_judge_the_way_it_was_described_to_the_model() -> None:
    """The docstring is the schema the model read; it is the only fair schema to judge against."""
    result = FakeResult([call("find_availability", '{"date": "el jueves"}')])

    described = bridge.tool_calls_of(result, {"find_availability": "Consulta la agenda."})

    assert described[0].description == "Consulta la agenda."
    assert bridge.tool_calls_of(result)[0].description is None


# --- test_case_for ----------------------------------------------------------


def test_the_case_judges_the_whole_turn_and_not_its_first_message() -> None:
    """The lesson from ms-2: the filler and the answer are one thing to the caller."""
    result = FakeResult(
        [
            message("Un momento, le consulto la agenda."),
            call("find_availability", '{"date": "el jueves"}'),
            message("Le quedan las once y las dos. ¿Cuál prefiere?"),
        ]
    )

    case = bridge.test_case_for(GOLDEN, conversation_of("Clínica Norte.", result))

    assert "Un momento" in case.actual_output
    assert "¿Cuál prefiere?" in case.actual_output


def test_the_case_carries_the_expected_tools_by_name_and_the_behaviour_as_context() -> None:
    result = FakeResult([call("find_availability", '{"date": "el jueves"}')])

    case = bridge.test_case_for(GOLDEN, conversation_of("", result))

    assert case.input == GOLDEN["input"]
    assert [t.name for t in case.expected_tools] == ["find_availability"]
    assert case.expected_tools[0].input_parameters is None
    assert case.context == [f"Expected behaviour: {GOLDEN['expected_behaviour']}"]


def test_a_greeting_golden_judges_the_opening_line_and_expects_no_call() -> None:
    """The greeting happens in on_enter, before any turn: there is nothing it could call."""
    conversation = Conversation(greeting="Clínica Norte, le atiende recepción. ¿En qué le ayudo?")

    case = bridge.test_case_for(GREETING_GOLDEN, conversation)

    assert case.actual_output == conversation.greeting
    assert case.tools_called == []
    assert case.expected_tools == []


def test_a_golden_that_must_not_call_still_reports_what_the_turn_did_call() -> None:
    """Expecting nothing and calling something is the failure the metric has to see."""
    result = FakeResult([call("find_availability", '{"date": "mañana"}')])
    golden = {
        "input": "¿cuánto cuesta?",
        "expected_behaviour": "Dice el precio.",
        "expected_tools": [],
    }

    case = bridge.test_case_for(golden, conversation_of("", result))

    assert case.expected_tools == []
    assert [t.name for t in case.tools_called] == ["find_availability"]


# --- the platform's clock is not the business's tool -------------------------


CLOCK = "fecha_y_hora_actual"
NO_BUSINESS_CALL = {
    "input": "hola, ¿qué día es hoy?",
    "expected_behaviour": "Dice el día sin tocar la agenda.",
    "expected_tools": [],
}


def scored_by_tool_correctness(case) -> float:
    """What DeepEval's deterministic ToolCorrectness makes of a case — no judge, no key."""
    metric = ToolCorrectnessMetric(threshold=0.9)
    metric.measure(case)
    return metric.score


def test_the_platform_clock_does_not_count_against_a_golden_that_expects_no_business_tool() -> None:
    """The ms-18 divergence that was never one: GPT asks the clock, Haiku does not."""
    result = FakeResult([call(CLOCK, "{}"), message("Hoy es martes 1 de septiembre.")])

    case = bridge.test_case_for(NO_BUSINESS_CALL, conversation_of("", result))

    assert [t.name for t in case.tools_called] == []
    assert scored_by_tool_correctness(case) == 1.0


def test_a_business_tool_the_golden_expected_is_still_missing_when_only_the_clock_ran() -> None:
    """The other half: the filter must not turn every turn into a passing one."""
    result = FakeResult([call(CLOCK, "{}"), message("El jueves le viene bien, seguro.")])

    case = bridge.test_case_for(GOLDEN, conversation_of("", result))

    assert [t.name for t in case.expected_tools] == ["find_availability"]
    assert scored_by_tool_correctness(case) < 0.9


def test_the_business_tools_of_a_turn_survive_the_filter_in_the_order_they_were_called() -> None:
    result = FakeResult(
        [
            call(CLOCK, "{}", call_id="c1"),
            call("find_availability", '{"date": "mañana"}', call_id="c2"),
            call("find_patient", '{"phone": "600"}', call_id="c3"),
        ]
    )

    kept = bridge.business_calls(bridge.tool_calls_of(result))

    assert [c.name for c in kept] == ["find_availability", "find_patient"]


def test_the_whole_call_case_still_shows_the_clock_to_the_graders_that_read_outputs() -> None:
    """Grounding reads a tool's OUTPUT as evidence: the date came off the clock, not the model."""
    result = FakeResult([call(CLOCK, "{}"), output("Hoy es martes 1 de septiembre de 2026.")])

    case = bridge.conversational_test_case_for(conversation_of("Clínica Norte.", result))

    called = case.turns[-1].tools_called
    assert [c.name for c in called] == [CLOCK]
    assert "martes" in called[0].output


# --- the project's own metrics ----------------------------------------------


def test_a_project_declares_its_metrics_next_to_its_goldens() -> None:
    metrics = bridge.project_metrics("clinica-norte", "reagendamiento")

    assert metrics.tool_correctness().threshold == 0.9
    assert metrics.argument_correctness().threshold == 0.8
    assert metrics.reception_line().threshold == 0.7


def test_the_tools_are_described_by_the_project_that_declares_them() -> None:
    """Read off the real agent, so a renamed tool breaks here and not inside an eval."""
    tc = fake_context("clinica-norte", "reagendamiento")

    described = bridge.tool_descriptions(tc)

    assert "find_availability" in described
    assert "agenda" in described["find_availability"]


def test_every_call_returns_a_fresh_metric() -> None:
    """A DeepEval metric holds the last score it measured; sharing one loses results."""
    metrics = bridge.project_metrics("clinica-norte", "reagendamiento")

    assert metrics.tool_correctness() is not metrics.tool_correctness()


# --- conversational_test_case_for -------------------------------------------


def test_a_run_becomes_a_transcript_that_opens_with_the_line_the_agent_opened_on() -> None:
    """The greeting happens in on_enter: a transcript starting with the caller is not the call."""
    conversation = conversation_of("Clínica Norte, ¿en qué le ayudo?", FakeResult([message("Ya.")]))

    case = bridge.conversational_test_case_for(conversation)

    assert [(t.role, t.content) for t in case.turns] == [
        ("assistant", "Clínica Norte, ¿en qué le ayudo?"),
        ("user", "hola"),
        ("assistant", "Ya."),
    ]


def test_an_assistant_turn_carries_the_model_s_calls_and_then_the_platform_s_writes() -> None:
    """`book_appointment` is the model asking for a yes; `book_slot` is the appointment moving."""
    result = FakeResult([call("book_appointment", '{"time": "11:00"}')])
    exchange = Exchange(
        input="sí",
        result=result,
        platform_calls=[
            PlatformCall(
                name="book_slot",
                args={"slot_id": "sl-1"},
                ok=True,
                result={"appointment_id": "ap-1"},
            )
        ],
    )

    case = bridge.conversational_test_case_for(Conversation(greeting="", exchanges=[exchange]))

    assert [t.name for t in case.turns[1].tools_called] == ["book_appointment", "book_slot"]
    assert case.turns[1].tools_called[1].output == "{'appointment_id': 'ap-1'}"


def test_a_platform_write_the_customer_s_system_rejected_says_so_to_the_judge() -> None:
    exchange = Exchange(
        input="sí",
        result=FakeResult([]),
        platform_calls=[PlatformCall(name="book_slot", args={}, ok=False)],
    )

    case = bridge.conversational_test_case_for(Conversation(greeting="", exchanges=[exchange]))

    assert case.turns[1].tools_called[0].output == bridge.REFUSED


def test_the_scenario_of_the_golden_that_drove_the_call_travels_onto_the_case() -> None:
    conversation = conversation_of("", FakeResult([message("Ya.")]))

    case = bridge.conversational_test_case_for(conversation, scenario="Cambia su cita", name="uno")

    assert case.scenario == "Cambia su cita"
    assert case.name == "uno"
