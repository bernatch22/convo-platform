"""Turn a headless run into DeepEval's vocabulary: what the agent said, what it called.

Decisions: docs/decisions/convo.testing.metrics.deepeval.md
"""

import importlib
import json
from collections.abc import Mapping, Sequence
from types import ModuleType
from typing import Any

from deepeval.test_case import ConversationalTestCase, LLMTestCase, ToolCall, Turn
from livekit.agents.llm import tool_context
from livekit.agents.llm import utils as llm_utils
from livekit.agents.voice.run_result import RunResult

from convo.domain.catalog import infrastructure_names
from convo.domain.context import TenantContext
from convo.testing.harness import Conversation, Exchange, PlatformCall, text_of

GREETING_TURN = "greeting"

# The three lines DeepEval writes per node into a DAG metric's verbose log; the rest of
# that log is the criteria and the rendered blocks, which nobody reads in a failure message.
NODE_LINES = ("Label:", "Verdict:", "Reason:")

PLATFORM_TOOL = (
    "Run by the platform itself against the customer's own systems — this is the call their "
    "booking system actually received, not a tool the model chose to call."
)
REFUSED = "refused: the customer's system rejected it and nothing was written"


def tool_descriptions(tc: TenantContext) -> dict[str, str]:
    """Every tool of every stage of the project, by name, described as the MODEL sees it."""
    return {
        tool_context.get_function_info(tool).name: _described(tool)
        for agent in _stages(tc)
        for tool in agent.tools
    }


def inputs_for(golden: Mapping[str, Any]) -> list[str]:
    """The user turns a golden needs: what has to be said first, then the turn it judges."""
    if golden.get("turn") == GREETING_TURN:
        return []
    return [*golden.get("before", []), golden["input"]]


def tool_calls_of(
    result: RunResult, descriptions: Mapping[str, str] | None = None
) -> list[ToolCall]:
    """Every tool the model called during one turn, in the order it called them."""
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


def business_calls(calls: Sequence[ToolCall]) -> list[ToolCall]:
    """The calls a golden is about: everything except the platform's own infrastructure."""
    platform = infrastructure_names()
    return [call for call in calls if call.name not in platform]


def call_named(calls: Sequence[ToolCall], name: str) -> ToolCall | None:
    """The first call to a NAMED tool in a turn, or None — never `tools_called[0]`."""
    return next((call for call in calls if call.name == name), None)


def test_case_for(
    golden: dict[str, Any],
    conversation: Conversation,
    descriptions: Mapping[str, str] | None = None,
) -> LLMTestCase:
    """One golden and the run it produced, as the single case every metric reads."""
    expected = [ToolCall(name=name) for name in golden.get("expected_tools", [])]
    context = [f"Expected behaviour: {golden['expected_behaviour']}"]
    # What the agent already knew when the judged turn arrived. Without it a judge scores
    # the turn as if the call had started there and reads every argument the model learnt
    # earlier — the patient's specialty, their name — as invented out of nothing.
    if golden.get("before"):
        context.append("Earlier in the call the patient said: " + " / ".join(golden["before"]))
    if golden.get("turn") == GREETING_TURN:
        return LLMTestCase(
            name=golden["input"],
            input=golden["input"],
            actual_output=conversation.greeting,
            tools_called=[],
            expected_tools=expected,
            context=context,
        )
    result = conversation.results[-1]  # the judged turn; `before` turns only get the call there
    return LLMTestCase(
        name=golden["input"],
        input=golden["input"],
        actual_output=text_of(result),
        tools_called=business_calls(tool_calls_of(result, descriptions)),
        expected_tools=expected,
        context=context,
    )


def turn_tool_calls(
    exchange: Exchange, descriptions: Mapping[str, str] | None = None
) -> list[ToolCall]:
    """Everything one turn called: the model's own tools, then the platform's writes."""
    return [
        *tool_calls_of(exchange.result, descriptions),
        *(_platform_call(call) for call in exchange.platform_calls),
    ]


def conversational_test_case_for(
    conversation: Conversation,
    descriptions: Mapping[str, str] | None = None,
    *,
    scenario: str | None = None,
    expected_outcome: str | None = None,
    name: str | None = None,
) -> ConversationalTestCase:
    """A whole headless run as the multi-turn case a ConversationalDAGMetric reads."""
    turns: list[Turn] = []
    if conversation.greeting:
        turns.append(Turn(role="assistant", content=conversation.greeting))
    for exchange in conversation.exchanges:
        turns.append(Turn(role="user", content=exchange.input))
        turns.append(
            Turn(
                role="assistant",
                content=text_of(exchange.result),
                tools_called=turn_tool_calls(exchange, descriptions),
            )
        )
    return ConversationalTestCase(
        turns=turns,
        scenario=scenario,
        expected_outcome=expected_outcome,
        name=name,
    )


def project_evals(tenant_id: str, project_id: str, module: str) -> ModuleType:
    """One module of a project's `evals/` package, imported by name."""
    return importlib.import_module(f"tenants.{tenant_id}.projects.{project_id}.evals.{module}")


def project_metrics(tenant_id: str, project_id: str) -> ModuleType:
    """The `evals/metrics.py` a project declares, imported by name."""
    return project_evals(tenant_id, project_id, "metrics")


def node_chain(metric: Any) -> list[str]:
    """Why a DAG metric scored what it scored: each node's label, verdict and one-line reason."""
    lines = str(getattr(metric, "verbose_logs", "") or "").splitlines()
    return [line.strip() for line in lines if line.strip().startswith(NODE_LINES)]


def _platform_call(call: PlatformCall) -> ToolCall:
    """One platform write as a ToolCall a judge can read, refusals included."""
    return ToolCall(
        name=call.name,
        description=PLATFORM_TOOL,
        input_parameters=call.args,
        output=str(call.result) if call.ok else REFUSED,
    )


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
    """The JSON arguments of a function call, as a dict a metric can read."""
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}
