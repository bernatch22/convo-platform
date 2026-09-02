# `convo.prompting.protocols`

The reasoning that used to live in the docstrings of `convo/prompting/protocols.py`; the code keeps one line per symbol.

## module

`core.security.control` is the machinery; this is the language half, kept apart
because a project's prompt imports it and nothing else in supervision.

**A whisper is not a document, it is somebody talking.** That sentence is the
whole finding of `tk-bc0122`, measured on Haiku 4.5 across both demo projects,
3 runs per cell, and it is the opposite of what `core.dates_note` found for the
session date — for a reason worth keeping in mind:

- the date only had to be AVAILABLE, so it goes in as a paired tool call and
  result. A tool result is evidence: nobody said it, there is nothing to answer.
- a steer has to be OBEYED. Delivered as that same tool pair it is read and
  filed and NOT acted on (1/3 on the case a mid-conversation instruction got
  3/3). Haiku obeys a speaker, not a file.

So the note stays in the framework's mid-conversation instruction channel
(`ChatContext.add_message(role="system")`), which livekit-agents 1.7.1 renders
to Anthropic as a `role="user"` turn wrapped in `<instructions>`
(`llm/_provider_format/utils.convert_mid_conversation_instructions`). It never
touches the top-level `system` param, so the cached prefix stays byte-identical
across a whisper — the constraint that made every other candidate hard.

**What still beat the whisper: the stage's own prompt.** With no protocol in
the prefix, a steer that contradicts the stage script is ignored by every
delivery there is (tienda-sur, «búscalo por el móvil» against a script that
asks for the order number first: 0/3 as an instruction, as a tool result, as an
assistant self-note, at the head or the tail of the context, and worded as an
order). Teaching the persona — in the CACHED prefix, where it costs nothing —
that such instructions exist and outrank the script turns the same cell into
3/3. That paragraph is `SUPERVISOR_PROTOCOL`, and a project without it gets a
whisper it may or may not obey.

**One thing no delivery buys: a sentence the caller did not ask for.** In
`inject` mode the agent is answering a caller and the stage script owns that
turn: «avísale del retraso» is ignored 0/3 (and not deferred — still absent two
turns later). The mode that works for it is `inject_and_speak`, which asks for a
turn whose only content IS the note: 3/3. That is the difference between
"change how you are doing this" and "say this now", and it belongs in the
desk's UI, not in a wording tweak.

Open source note: `SUPERVISOR_PROTOCOL` is Spanish because both demo tenants
are; a project in another language writes its own and appends that instead.
