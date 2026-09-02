# `convo.testing.metrics.deepeval`

The reasoning that used to live in the docstrings of `convo/testing/metrics/deepeval.py`; the code keeps one line per symbol.

## module

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
- `expected_tools` is about the BUSINESS's tools, so the case ToolCorrectness
  reads carries the business's calls. A golden that expects nothing expects the
  agenda to be left alone; it does not expect the agent to be struck dumb, and
  the platform's own clock is not a name any golden should have to list. The
  filter is `business_calls`, it is driven by `ToolSpec.infrastructure`, and it
  applies to `test_case_for` alone: `turn_tool_calls` and the conversational
  case keep every call, because the grounding metric reads a tool's OUTPUT as
  evidence and the clock reading is the evidence for what day it is.

## tool_descriptions

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

## inputs_for

A golden about a later stage carries the turns that get the call there under
`before`. They are run, never judged: a rescheduling call cannot ask about
free hours before it knows whose appointment it is, so the alternative to
replaying the identification is a golden that judges the wrong stage.

## tool_calls_of

Each call carries what the model passed, what came back, and (when
`descriptions` is given) what the tool said it was for.

## business_calls

`expected_tools` names the tools of the BUSINESS — the agenda, the order
book — and a golden that lists none of them is saying "this turn must not
touch the business", not "this turn must call nothing at all". Until this
filter existed, a model that asked what day it is before answering scored
0.0 on such a golden while a GEval judge, reading the same turn, wrote that
the tool was "correctly not invoked" (docs/evals.md §9): two goldens of the
clinic's ms-18 matrix on gpt-5.4-mini, a divergence that was never a
behaviour difference.

What counts as infrastructure is DECLARED, never matched: a `ToolSpec` with
`infrastructure=True`, which today is `core.tools.catalog.CLOCK` and
tomorrow is whatever a project marks. Nothing here knows a tool name.

## call_named

Index is not identity, and it stopped being a usable stand-in the day every
stage inherited the clock (`TenantAgent.fecha_y_hora_actual`). A turn that
asks the agenda about "mañana" now often calls the clock first to find out
what "mañana" is, so an assertion reading the first call was reading the
clock's arguments — no `date` in them at all — and failing a turn that had
asked exactly the right question. A suite that wants the agenda asks for the
agenda; the ORDER of the calls, when it matters, is ToolCorrectness's job.

## test_case_for

A golden marked `turn: greeting` is about the line the agent opens the call
with, which happens in `on_enter` before any user input: its output is
`Conversation.greeting` and it called nothing, because there was no turn in
which to call anything. Every other golden is one user input and the turn
that answered it.

The case is NAMED after the golden that drove it. DeepEval falls back to
`test_case_<n>` otherwise, and the eval matrix joins two models' runs on
that name: a table whose findings read «test_case_0» tells a reviewer which
position diverged, not which golden.

`expected_tools` is a list of tool names in the golden — names only, never
arguments: what the model should pass is judged by ArgumentCorrectness or
by an assertion the project writes itself, and an expected argument written
here would show up in the report as a value the model never had to produce.

`tools_called` is what the turn called MINUS the platform's infrastructure
(`business_calls`), because this is the case ToolCorrectness scores against
a list of the business's tools. Nothing is hidden from the graders that want
the clock: the whole-call case keeps every call, and so does
`turn_tool_calls`.

## turn_tool_calls

Both, and in that order, because they answer different questions. The
model's calls say what it decided to do; the platform's say what the
customer's systems were actually told. A metric about consent reads the
second — `book_appointment` is the model asking for a yes, `book_slot` is
the appointment moving — and the names are kept as they are so a criterion
can name one without hitting the other.

## conversational_test_case_for

One `Turn` per side of each exchange, in the order they were spoken, with
the assistant's turns carrying what that turn called. The opening line goes
in first as an assistant turn of its own: it happens in `on_enter`, before
anybody has said anything, and a transcript that starts with the caller
talking into silence is not the call that took place.

`scenario` and `expected_outcome` travel from the golden that drove the
conversation, so the report a reviewer opens says what this call was
supposed to be, not just what was said.

## project_evals

Imported the way `core.registry` imports a tenant — by name, at call time —
so core still compiles with no customer folder on disk, and a tenant
directory name with a hyphen in it is still reachable.

## project_metrics

Metrics are project data, like prompts and goldens: what "a good reply"
means for a clinic's reception is not what it means for a shop's returns
desk.

## node_chain

A metric whose nodes are computed is built with `include_reason=False` —
DeepEval's summary is generated, and it would be the only model call left in
a graph that has none. What such a metric still has is its chain, buried in
a verbose log that also contains every criterion and every rendered block.
These are the lines a person reads; the rest is for `deepeval test run -v`.

`convo/sessions.py` keeps its own copy of the filter on purpose: the CLI
must list and show sessions with no judge stack installed, so it never
imports this module at the top.

## _arguments

A payload that is not a JSON object is kept verbatim under `_raw` instead
of raising: a malformed call is exactly the kind of thing an eval exists to
show, and a crash here would hide it behind a stack trace.
