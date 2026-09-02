# `convo.agents.stage`

The reasoning that used to live in the docstrings of `convo/agents/stage.py`; the code keeps one line per symbol.

## module

A conversation is a sequence of stages, one Agent each. LiveKit does not copy
history across a handoff, so the stage that enters writes a one-line summary of
the stage it replaces into its own chat context before saying anything: what
the caller already told us travels, the whole transcript does not.

Three of the framework's nodes are overridden here, once, for every project:
`stt_node` refuses a transcript no audio can account for, `transcription_node`
reads the agent's words on their way out and times them in the log, and
`on_user_turn_completed` is the turn boundary — where a supervisor's whisper is
applied, where a human holding the line cancels the reply, and where a murmur
that landed on the agent's voice is dropped. All of it is audit and turn-taking,
not business, so no stage overrides them.

The platform's own verbs reach a stage two different ways, and the difference
is whether they can be ABSENT. The clock is a method: every stage of every
project has it, forever. The transfer is layered into `tools=` at construction
(`core.agents.human`), because a project that names no `transfer_number` must
never be shown a tool it cannot run — the model cannot reach for a verb it was
never given.

## TenantAgent.on_enter

The very first stage of a session speaks the project's `greeting`
verbatim when one is set: a caller hears the business immediately
instead of waiting an LLM ttft for a sentence that never changes
(measured on a real phone call: 1.9 s of silence), and it is the one
sentence a supervisor edits from the console — a paraphrasing model
would make it uneditable. `say` puts the line in the chat history so
the model knows what was said. Later stages, and a project with no
greeting, still open with `generate_reply` — and that is the shape the
date reaches the model in front of, so `_read_the_clock` runs first.

## TenantAgent.stt_node

A streaming STT invents sentences over a silent line — Soniox put a
final "Thank you." into the human's call AJ_rt86KogpPxDa while nobody
had spoken, and the agent answered it. `core.stt_gate` measures the very
frames going into the STT and refuses a transcript with no voiced audio
behind it; the refusal is a `stt.phantom` line in the log, never a
silent drop, because a gate nobody can audit is worse than the bug.

This is the last seam where a transcript can still be stopped: one node
later it is an interruption, a user turn and a reply. The price of
standing here is the framework's STT-pipeline reuse across a handoff
(`AgentActivity._detach_reusable_resources` reuses it only for the
DEFAULT `stt_node`), so each stage opens its own STT stream. Frames
queue while it connects and none are lost — a handoff is the moment the
agent takes the floor, not the caller.

## TenantAgent.transcription_node

Every delta goes on exactly as it arrived — this node is where a
project could rewrite what the caller reads, and rewriting it is
precisely what an audit log must not do. With
`use_tts_aligned_transcript=True` and ElevenLabs `sync_alignment=True`
the deltas are `TimedString`s carrying `end_time`; `TimedWords` batches
them into one `tts.word` event per sentence.

## TenantAgent.on_user_turn_completed

This is the framework's turn boundary, which makes it the one safe
moment to swap the agent's chat context: a whisper queued while the
agent was mid-sentence is applied here, before the reply is built and
never during one. Then, while a supervisor holds the line,
`StopResponse` cancels every reply — the turn still lands in the
history, which is what `release` reads back to the model, but the
caller hears the human and not the agent (agents#3645).

The last filter is the old one: "vale" while the agent is mid-sentence
is agreement, not a question, and a reply to it is a filler the caller
hears as a mistake. It cannot cancel the interruption —
`core.barge_in` documents where each of the two filters sits in the
framework's turn pipeline, and why `InterruptionOptions.min_words` is
the one that saves the audio.

## TenantAgent.hand_off

Default to no line. A tool that returns text alongside the next stage
makes the stage that is LEAVING answer with it, and the stage arriving
then speaks in its own `on_enter` — two turns, one after the other, and
on a phone call that is the same thing said twice. What the next stage
needs to know travels in `summary()`, not in a farewell sentence.

Pass `said` only when the leaving stage genuinely has the last word.

## TenantAgent._own_voice

Nothing at all is the important half: with no key in
`Project.stage_voices` the agent is built without a `tts=`, so the
session's own TTS is used and a project that never asked for a second
voice is byte for byte where it was. The framework builds one TTS per
agent that names one, at construction — a stage is built when the
conversation reaches it, so a voice nobody is handed to is never
connected.

## TenantAgent._read_the_clock

The system prompt cannot carry the date (the cached prefix must stay
byte-identical) and a model with no calendar invents one when asked
"¿hoy qué día es?" — it said "viernes" on a Saturday, on a real call.
It cannot be a system message either: the framework rewrites every
system item after the first into a USER message, and Haiku then opened
the call by answering it. `core.dates_note` carries the measurement and
the why; here it is two paired tool items, written before the greeting.
