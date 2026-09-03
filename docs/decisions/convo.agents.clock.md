# `convo.agents.clock`

The reasoning that used to live in the docstrings of `convo/agents/clock.py`; the code keeps one line per symbol.

## module

The system prompt must stay byte-identical or Haiku's cache is gone, so the
date cannot live there; the tools resolve "mañana" against `tc.today`, but a
patient asking "¿hoy qué día es?" is talking to the MODEL, and a model with
no calendar invents one (it said "viernes" on a Saturday, on a real call).
The time of day changes mid-call — a note with minutes would be stale before
the goodbye — so the clock is also a TOOL (`TenantAgent.fecha_y_hora_actual`)
the model calls at the moment it is asked, recomputed every single time.

**How the date reaches the model is the whole of this module.** It was a
`system` message added to the chat context after the prefix, and that is a
turn: livekit-agents 1.7.1 keeps only the FIRST system item as a system item
(`llm/_provider_format/utils.convert_mid_conversation_instructions`) and
rewrites every later one as a **user** message wrapped in `<instructions>`.
The agent's own prompt is that first item, so the date arrived at Anthropic as
the opening line of the CALLER. Haiku answered it — «Entendido. Hoy es martes 1
de septiembre de 2026. Estoy listo para atender las llamadas de la Clínica
Norte» — 5 times out of 6 measured (tk-097125), on both demo projects, where
gpt-5.4-mini never did. It is not a prompt bug: nothing addressed to a model as
a user turn can be reliably told not to be answered.

So the date is delivered as `clock_reading`: the session's own call to
`fecha_y_hora_actual` and its result, paired, written into the context before
the first turn. A tool result is the one shape in a chat context that is
evidence rather than speech — nobody said it, so there is nothing to answer —
it keeps its position, and it stays out of the cached system prefix, which is
the constraint that made a note necessary in the first place. Measured against
dropping the note entirely and letting the model call the clock itself: that
also fixes the opening line, but it buys a tool round-trip on every date
question and, two times in three, an audible "espere un momento, le digo la
fecha exacta" before an answer the session already had at second zero.

Open source note: Spanish only because both demo tenants speak it; a project
in another language needs its own word lists behind `convo.agents.clock.date_note`;
there is no per-project hook yet.

## clock_reading

Two paired items — the call and its result — so the context carries the
date as evidence and not as somebody's turn. The pair is inserted, never
executed: the platform already knows the day, and a round-trip through the
executor would only spend a turn to learn it.

`call_id` is fixed (one reading per session) and free of dots on purpose:
Anthropic validates `tool_use.id` against `^[a-zA-Z0-9_-]+$` and refuses
the whole request with a 400 for a `lk.session.date`.
