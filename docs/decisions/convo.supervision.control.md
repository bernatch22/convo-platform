# `convo.supervision.control`

The reasoning that used to live in the docstrings of `convo/supervision/control.py`; the code keeps one line per symbol.

## module

`core.security.monitor` is the road a verb travels; this is what happens when
it arrives. One `SupervisorControl` per job, built with the session it steers,
hung on the `TenantContext` so every stage already carries it.

**A whisper is never applied mid-generation.** The model is already streaming
a sentence built from a context; swapping that context underneath it is how a
tool call loses its result and the next request comes back 400. So a steer is
QUEUED and flushed at a turn boundary — either immediately, when the floor is
free, or from `TenantAgent.on_user_turn_completed`, which is the framework's
own boundary and runs before the reply is generated. The swap itself mirrors
`_enqueue_reply`: copy the context, add the note as a mid-conversation
instruction, `sanitize_tool_pairing`, hand the whole thing to `update_chat_ctx`.

**Whether the model then obeys it is not a matter of delivery.** That was
measured, cell by cell, in `core.security.protocol` — read it before changing
`NOTE_ROLE` or moving the note into a tool result, because the answer is the
opposite of the one `core.dates_note` reached for the session date, and the
lever that actually decides it is a paragraph in the project's cached prefix.

**Takeover is a mute, not a pause.** There is no `session.pause()` in
livekit-agents 1.7.1 (grepped; absent). What exists is the recipe below:
`interrupt(force=True)` cuts the sentence in flight, `resume_false_interruption`
is held off so the framework does not resume it by itself, and
`TenantAgent.on_user_turn_completed` raises `StopResponse` while `muted` — so
turns keep landing in the history and none of them is answered. That last part
is the point: the STT stays on THROUGHOUT, which is what makes the human's
interval readable at release. `deaf=True` is the opposite trade — audio input
off, nothing transcribed, nothing to resume with — and it is the caller's
choice, not the default, because "the agent comes back not knowing what was
said" is a worse failure than "the agent overheard a card number" for every
project that has not said otherwise.

Known upstream limits, all three relevant here and all three cited on the card:
agents#3820 (`generate_reply` only APPENDS, so a hard course-correction has to
be the `update_chat_ctx` swap and not an instruction), #3645 (`StopResponse`
skips the turn and nothing else), #5038 (interrupted text can be dropped from
history — so `release` checks whether the interval is really there rather than
assuming, and says so in the note when it is not).

Open source note: the whole file is framework-coupled but tenant-free — a
stranger gets human-in-the-loop steering for any livekit-agents deployment by
copying this and `core.security.supervisor`.

## SupervisorControl.apply

The gate is here and not in either road, so an RPC from a browser and a
packet from the control plane are refused by exactly the same line.

## SupervisorControl.steer

→ `{"verb", "queued": bool, "spoke": bool}` — `queued` is True when the
agent was mid-sentence and the note is waiting for the boundary.

`mode` is the honest half of the API. `inject` bends the agent's next
answer — «no le pidas el teléfono», «búscalo por el móvil» — and it
cannot make the agent volunteer something the caller did not ask for,
because the stage prompt owns that turn. A note the supervisor wants
SAID («avísale de que hoy vamos con retraso») needs `inject_and_speak`,
which buys a turn of its own for it.

## SupervisorControl.takeover

→ `{"verb", "muted", "deaf", "interrupted", "already"}`. Idempotent — a
second takeover from a desk that lost its websocket changes nothing.

## SupervisorControl.release

→ `{"verb", "muted": False, "heard": bool, "turns": int, "already"}`.
`heard` is False when nothing of the interval reached the history
(agents#5038) — the note the agent gets then says so instead of
pretending, because an agent that acts on an interval it never saw is
the worst outcome this verb has.

## SupervisorControl.transfer

→ `{"verb", "mode", "outcome", "to", "ok", …}`, the same payload the log
line carries. `ok=False` is an ANSWER, not an error: it means the
transfer did not happen and the caller is still here, being told so.
Only a refusal before anything was dialled raises, so a desk can tell
"your number was wrong" from "his phone was busy".

A warm transfer ends muted. Once the colleague and the caller can hear
each other the agent is a third voice in a two-person call, so the same
`release` that follows a takeover is what would bring it back.

## SupervisorControl.flush

False when there was nothing to write, or no agent to write it to — a
console run and a chat harness both reach this with neither.

## SupervisorControl._interrupt

`force=True` is deliberate: a speech created with
`allow_interruptions=False` — a confirmation being read out, say — is
exactly the one a human taking the line most needs to stop.
