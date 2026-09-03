# `convo.agents.human`

The reasoning that used to live in the docstrings of `convo/agents/human.py`; the code keeps one line per symbol.

## module

One `@function_tool`, module-level rather than a method of `TenantAgent`, for
the only reason that matters here: a method is on every stage of every project
forever, and this verb has to be able to be ABSENT. A project that names no
`transfer_number` never sees it in its tool list — not greyed out, not failing
politely, absent — which is the same promise `convo.session.pipeline` makes about a
provider whose key this box does not carry.

It is a thin door on purpose. The decision of what a transfer costs and where
it goes is `convo.telephony.human`; the run is `convo.adapters.human`, reached
through the executor like every other write, so the guard, the timeout and the
project's own failure sentence all apply. What is left here is the docstring —
and the waiting.

**The docstring is where the trigger rules live, and that is not an accident.**
A tool's description is loaded into the system prompt anyway, so a project
paragraph repeating "call it when…" pays for the same sentence twice on every
stage, including the stages that will never transfer anybody. It is written in
the register Anthropic's current guidance asks for — «úsala cuando…», not
«CRITICAL: DEBES llamarla» — because aggressive triggering language makes a
modern model overtrigger, and it says what to DO rather than listing what not
to. `convo.telephony.human.PROTOCOL` keeps only the half a description cannot
carry: that the announcement is a spoken turn.

**The waiting is the load-bearing line.** A model that announces «le paso con
un compañero, un momento» and calls the tool in the same turn has queued that
sentence for TTS, not spoken it. REFER the leg first and the carrier takes the
call mid-word: the caller is handed to a colleague having heard nothing, which
is exactly the abandonment the announcement exists to prevent.
`ctx.wait_for_playout()` is the framework's answer, and it costs nothing on a
channel with no audio.

## transfer_tools

The whole of the `unavailable_reasons` idiom on the agent's side: one read
of the project, at the moment the stage is built, and the model's tool list
either has the verb or has never heard of it.
