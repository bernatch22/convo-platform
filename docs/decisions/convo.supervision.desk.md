# `convo.supervision.desk`

The reasoning that used to live in the docstrings of `convo/supervision/desk.py`; the code keeps one line per symbol.

## module

`mint_supervisor` hands out a ticket; a ticket is an intention, not a
presence. What belongs in a compliance log is the arrival — so the desk asks
the SFU who is actually in the room before it writes anything down, and reads
the capability off the SFU's own copy of the signed token
(`attributes["cap"]`, put there by `core.auth.mint_supervisor`) rather than
off anything the browser sends. A client that lies about its capability is
lying to a field nobody reads.

The announcement goes to the **agent alone**. Broadcasting it would deliver a
data packet saying "a supervisor joined" straight into the caller's browser,
which is the one thing this whole feature exists not to do — so the
destination is the room's agent participant, by identity, and a room with no
agent in it is announced to nobody.

Why an announcement at all: measured on this box (livekit-server v1.9.1), a
hidden participant fires no `participant_connected` anywhere, so the agent
cannot see the arrival even if it wanted to. The control plane can — it holds
the API key — and the packet is how the fact reaches the process that owns the
caller's log, where the `seq` is allocated. One writer, one sequence, one story.

`command` is the same packet carrying an ORDER rather than a fact: a steer, a
takeover, a release or a transfer aimed at the room's agent, server-side. A browser does
not need it — it holds a `whisper` ticket and calls the agent's RPC directly —
but a control plane does: an escalation rule, a compliance trigger or a
`curl` from a terminal has no room connection to perform RPC over. Both roads
end at `core.security.control.SupervisorControl.apply`, which asks the same
`is_supervisor` question of the same identity.

## entered

→ `{"identity", "capability", "hidden", "announced"}`

`hidden` is the SFU's answer, not ours — it is the honest way to show a
supervisor that the caller genuinely cannot see them, and it is what the
desk puts on screen. `announced` is False when the room holds no agent to
tell, which is not an error: the call has no log being written either.

Raises `NotInRoom` when the identity is not in the room (a ticket that was
minted and never used), and `RoomsUnreachable` when the SFU cannot be asked.

## command

→ `{"verb", "identity", "sent": True}` — the agent applies it and writes the
log line; this side never hears the outcome, because the log is the outcome.

The identity is checked against the SFU's own participant list first: a
verb from a `sup:` who is not actually in the call is a ticket somebody
kept, and the whole point of the short TTL is that it should not work.

Raises `NotInRoom` when the supervisor or the agent is not there,
`ValueError` for a verb this door does not forward, and `RoomsUnreachable`
when the SFU cannot be asked.
