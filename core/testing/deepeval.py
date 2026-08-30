"""Turn a headless run into DeepEval's vocabulary: what the agent said, what it called.

A `RunResult` is LiveKit's account of one turn — an ordered list of messages,
function calls, tool outputs and handoffs. DeepEval scores an `LLMTestCase`:
one input, one output, a flat list of `ToolCall`s. This module is the only
place that knows how to get from one to the other, so a project's eval suite
reads goldens and metrics and nothing else.

Deliberately NOT re-exported from `core.testing`: importing deepeval drags in a
judge stack that the unit ring must not pay for on every `pytest -m unit`.
A suite that scores imports this module by name; the harness stays free of it.

Three rules the conversion follows, each one paid for by an eval that failed
for the wrong reason:

- the output is the WHOLE turn, not its first message. Haiku says "un momento,
  le consulto la agenda" before calling a tool and answers once the result is
  back; a judge handed only the first message scores the filler.
- the arguments are what the MODEL produced, verbatim. The tool resolves
  "el jueves" into a date afterwards, so a case that stored the resolved value
  would be scoring the platform's arithmetic instead of the model's choice.
- a `ToolCall` carries the tool's description and the output it returned, not
  just its name. A judge shown a bare call has to guess what the tool wanted
  and cannot tell an hour read off the agenda from an hour invented — and it
  guesses wrong, confidently, in both directions.
"""

import importlib
import json
from collections.abc import Mapping
from types import ModuleType
from typing import Any

from deepeval.test_case import LLMTestCase, ToolCall
from livekit.agents.llm import tool_context
from livekit.agents.llm import utils as llm_utils
from livekit.agents.voice.run_result import RunResult

from core.context import TenantContext
from core.testing.harness import Conversation, text_of

GREETING_TURN = "greeting"


def tool_descriptions(tc: TenantContext) -> dict[str, str]:
    """Every tool of every stage of the project, by name, described as the MODEL sees it.

    Every stage, not just the entry one: from ms-3 a conversation moves through
    several agents and the turn a golden judges may be answered by any of them.
    A project that declares no stages is asked for its entry agent, which is the
    same thing when there is only one.

    A tool docstring in this codebase is the schema Claude reads before
    deciding whether to call — so it is also the only fair thing to show a
    judge asked whether the arguments were right. Without it the judge invents
    a contract: shown `find_availability(date="el jueves")` and nothing else,
    it decided the tool "requires YYYY-MM-DD" and failed a call the tool
    documents as correct.

    The per-argument rules are appended, not just the summary. LiveKit splits a
    docstring in two — the prose becomes the tool description, the `Args:`
    section becomes the JSON schema of the parameters — and it is the second
    half that says "the day in the patient's own words". A judge shown only the
    first half made the same mistake twice.
    """
    return {
        tool_context.get_function_info(tool).name: _described(tool)
        for agent in _stages(tc)
        for tool in agent.tools
    }


def inputs_for(golden: Mapping[str, Any]) -> list[str]:
    """The user turns a golden needs: what has to be said first, then the turn it judges.

    A golden about a later stage carries the turns that get the call there under
    `before`. They are run, never judged: a rescheduling call cannot ask about
    free hours before it knows whose appointment it is, so the alternative to
    replaying the identification is a golden that judges the wrong stage.
    """
    if golden.get("turn") == GREETING_TURN:
        return []
    return [*golden.get("before", []), golden["input"]]


def tool_calls_of(
    result: RunResult, descriptions: Mapping[str, str] | None = None
) -> list[ToolCall]:
    """Every tool the model called during one turn, in the order it called them.

    Each call carries what the model passed, what came back, and (when
    `descriptions` is given) what the tool said it was for.
    """
    outputs = {
        event.item.call_id: event.item.output
        for event in result.events
        if event.type == "function_call_output"
    }
    return [
        ToolCall(
            name=event.item.name,
            description=(descriptions or {}).get(event.item.name),
            input_parameters=_arguments(event.item.arguments),
            output=outputs.get(event.item.call_id),
        )
        for event in result.events
        if event.type == "function_call"
    ]


def test_case_for(
    golden: dict[str, Any],
    conversation: Conversation,
    descriptions: Mapping[str, str] | None = None,
) -> LLMTestCase:
    """One golden and the run it produced, as the single case every metric reads.

    A golden marked `turn: greeting` is about the line the agent opens the call
    with, which happens in `on_enter` before any user input: its output is
    `Conversation.greeting` and it called nothing, because there was no turn in
    which to call anything. Every other golden is one user input and the turn
    that answered it.

    `expected_tools` is a list of tool names in the golden — names only, never
    arguments: what the model should pass is judged by ArgumentCorrectness or
    by an assertion the project writes itself, and an expected argument written
    here would show up in the report as a value the model never had to produce.
    """
    expected = [ToolCall(name=name) for name in golden.get("expected_tools", [])]
    context = [f"Expected behaviour: {golden['expected_behaviour']}"]
    # What the agent already knew when the judged turn arrived. Without it a judge scores
    # the turn as if the call had started there and reads every argument the model learnt
    # earlier — the patient's specialty, their name — as invented out of nothing.
    if golden.get("before"):
        context.append("Earlier in the call the patient said: " + " / ".join(golden["before"]))
    if golden.get("turn") == GREETING_TURN:
        return LLMTestCase(
            input=golden["input"],
            actual_output=conversation.greeting,
            tools_called=[],
            expected_tools=expected,
            context=context,
        )
    result = conversation.results[-1]  # the judged turn; `before` turns only get the call there
    return LLMTestCase(
        input=golden["input"],
        actual_output=text_of(result),
        tools_called=tool_calls_of(result, descriptions),
        expected_tools=expected,
        context=context,
    )


def project_metrics(tenant_id: str, project_id: str) -> ModuleType:
    """The `evals/metrics.py` a project declares, imported by name.

    Metrics are project data, like prompts and goldens: what "a good reply"
    means for a clinic's reception is not what it means for a shop's returns
    desk. Imported the way `core.registry` imports a tenant — by name, at call
    time — so core still compiles with no customer folder on disk.
    """
    return importlib.import_module(f"tenants.{tenant_id}.projects.{project_id}.evals.metrics")


def _stages(tc: TenantContext) -> list[Any]:
    """Every stage the project declares, or its entry agent when it declares none."""
    if hasattr(tc.project, "stages"):
        return tc.project.stages(tc)
    return [tc.project.entry_agent(tc)]


def _described(tool: Any) -> str:
    """A tool's whole contract as one block of text: what it is for, then each argument."""
    schema = llm_utils.build_legacy_openai_schema(tool)["function"]
    properties = schema.get("parameters", {}).get("properties", {})
    lines = [f"- {name}: {spec.get('description', '')}" for name, spec in properties.items()]
    if not lines:
        return schema.get("description", "")
    return schema.get("description", "") + "\n\nArgumentos:\n" + "\n".join(lines)


def _arguments(raw: str) -> dict[str, Any]:
    """The JSON arguments of a function call, as a dict a metric can read.

    A payload that is not a JSON object is kept verbatim under `_raw` instead
    of raising: a malformed call is exactly the kind of thing an eval exists to
    show, and a crash here would hide it behind a stack trace.
    """
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}
