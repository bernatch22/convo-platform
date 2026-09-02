# `convo.telephony.handover`

The reasoning that used to live in the docstrings of `convo/telephony/handover.py`; the code keeps one line per symbol.

## module

`core.telephony.transfer` knows how to move a call. This knows what everybody
hears while it happens, and it exists because the two failure modes of a
transfer are both about sound, not about SIP:

- **A transfer that fails in silence.** The REFER is refused, the caller is
  still on the line, and the agent — which believes the call is over — says
  nothing at all. So every failing path here ends by putting a note in the
  agent's own context and asking it for a turn: the caller is told, in the
  same voice, that the colleague could not be reached.
- **A briefing the caller can hear.** The warm path cuts the agent's audio to
  the caller BEFORE it dials anybody, so the summary the model gives the
  colleague is spoken into a line the caller is no longer subscribed to
  (`core.telephony.isolation`, measured). The bridge at the end is the same
  call, undone.

Warm ends in a takeover, and that is deliberate: once the human and the caller
are hearing each other, the agent answering turns would be a third voice in a
two-person conversation. `SupervisorControl.transfer` mutes it, and the same
`release` that hands the line back after a whisper hands it back after this.

Open source note: `Handover` is the only file in the package that touches
`livekit.agents` — the transfer itself is framework-free. A deployment on
another agent framework replaces this file and keeps the other three.

## Handover.run

→ an `Outcome`. Raises `TransferRefused` only when nothing was
attempted — an unknown mode, no room, no caller, a destination that is
not a number — because that is the one case where the call is exactly
as it was and the desk should be told so instead of the caller.

## Handover.refer

The same one API call as `run(COLD, …)` with two things deliberately
missing. There is no hold line, because the agent announced the handover
itself in the turn that called the tool — `core.telephony.human.PROTOCOL`
is what teaches it to, and a platform line on top of it is the same
sentence said twice on a phone call. And there is no `_explain`, because
the tool's own return value is what tells the caller: a failure comes
back to the model as a result it must act on, in the same turn, instead
of as a note queued for the next one.

→ an `Outcome`, `ok=False` meaning the caller never moved. Raises
`TransferRefused` when nothing was attempted at all.

## Handover.join

A browser caller has no SIP leg a REFER could move, so the phone comes
to them instead: `CreateSIPParticipant` dials the project's number and
the human who answers arrives as one more participant in the same room.
No hold line and no briefing — the agent announced the handover in the
turn that called the tool, and once the two can hear each other its only
remaining job is silence (`core.adapters.human` mutes it).

→ an `Outcome`. Raises `TransferRefused` only when nothing was even
attempted — no outbound trunk on this box (the message names
`SIP_OUTBOUND_TRUNK_ID`), no room, no caller, a destination that is not
a number — always BEFORE anybody's phone has rung.

## Handover.on_a_phone

A browser voice session and a chat both have a room and a caller; what
neither has is a leg the carrier can take over. Asked before anything is
promised, this is the difference between an honest "I cannot transfer
this" and a REFER the SFU refuses mid-call.

## Handover._explain

The note is written into the context BEFORE the turn is asked for:
`generate_reply` only appends instructions (agents#3820), so a model
that has not been told the transfer failed will happily carry on as if
the caller had already been passed on.
