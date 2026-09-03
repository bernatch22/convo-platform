# `convo.supervision.monitor`

The reasoning that used to live in the docstrings of `convo/supervision/monitor.py`; the code keeps one line per symbol.

## module

A supervisor entering a live call must be two things at once. It must be
**invisible** — the caller is never told, and the agent must not greet, must
not re-plan, must not so much as notice — and it must be **on the record**,
because a second human hearing a stranger's call is exactly the fact an audit
comes looking for. Those two pull in opposite directions, and this module is
where they are reconciled: one `supervisor.join` in the caller's own log, and
no other consequence anywhere.

Two roads lead here, and both end at the same `entered`:

1. `participant_connected`, for a supervisor the SFU *does* announce (a
   `takeover`, which is not hidden). The handler exists to say out loud that a
   `sup:` arrival is not a caller — any greet-on-join a project adds later
   must go through `is_supervisor` first, and the LiveKit example that greets
   every joiner is precisely the bug this prevents.
2. a packet on the `supervisor` topic sent by the control plane with its own
   API key, for the hidden case — where the SFU announces nothing at all.

Measured on this box (livekit-server v1.9.1, `tmp/probe_hidden.py`): a
participant that joins with `hidden=True` fires **no** `participant_connected`
on the other clients and never appears in their `remote_participants`; the
server-side `list_participants` sees it perfectly. So road 1 alone would log
nothing for a listening supervisor — the invisibility is real, and road 2 is
what keeps it auditable anyway.

The trust boundary is the same one `convo.supervision.supervisor` states: a packet
whose `participant` is None came from a server SDK holding the API key, and
nothing a participant sends can look like that (measured too,
`tmp/probe_channel.py`). A `{"verb": "join"}` from a browser arrives with an
identity attached and is dropped.

The other four verbs — `steer`, `takeover`, `release`, `transfer` — are the
same idea pointed the other way: they DO change the conversation, so they reach
`convo.supervision.control.SupervisorControl` and never touch the session from
here. Two roads again, and on purpose:

3. `supervisor.steer` / `.takeover` / `.release` / `.transfer` as **RPC** on the agent's own
   participant. This is the road a supervisor's browser uses, and the reason
   the trust anchor works: the SFU puts `caller_identity` on the invocation
   off the JWT it verified, so `is_supervisor` is asking about a signature and
   not about a field somebody typed. The RPC method names ARE the audit kinds
   in `convo.supervision.supervisor` — one string, one verb, one log line.
4. the same `supervisor` topic as the join, for a control plane that would
   rather whisper server-side (an escalation rule, a compliance trigger) than
   hold a browser open. Same `participant is None` anchor, same handler.

Open source note: "log the second human, tell the agent nothing" is the whole
of live-monitoring compliance for any LiveKit deployment. The reusable half is
this file plus `convo.supervision.supervisor`; the tenant half is only which log
the event lands in.

## SupervisorWatch

Held by the job for as long as the job lives, which is exactly as long as
the call. `seen` is what makes the two roads idempotent: a `takeover`
supervisor is both announced by the SFU and announced by the control
plane, and one human entering one call is one line in the log.

## SupervisorWatch.entered

The return value is for tests and for the caller's own logging — the
agent itself never reads it, because there is nothing for the agent to
do about a supervisor being there.

## SupervisorWatch.on_participant

Ignoring is the behaviour. Nothing in this method reaches the session,
the agent or the LLM — a supervisor walking in changes no turn, no
stage and no prompt.

## SupervisorWatch.on_packet

`packet.participant is None` is the whole of the check. The SFU fills
that field in for every participant-sent packet and leaves it empty
only for one sent with the deployment's API key, so a browser cannot
forge a supervisor's arrival by publishing on this topic.

## SupervisorWatch.spawn

The room's `data_received` handler is synchronous and the verbs are
not, so the work becomes a task on the job's own loop. Nothing waits
for it: the control plane already has its 202, and what the verb did
lands in the log either way.

## watch_supervisors

Call it once per job, with the room the job runs in. A room that cannot be
subscribed to (the console, a test harness, a headless session) still gets
a watch back, so a caller never has to write an `if` about it — and with no
`control` the job simply has no verbs, which is what a console run wants.

## register_verbs

The gate is `SupervisorControl.apply`, which asks `is_supervisor` of the
`caller_identity` the SFU read off the JWT — so a caller, an observer or
anyone else who guessed the method name is refused before a single word
reaches the conversation.

## verb_handler

Every refusal comes back as an `RpcError` the browser can read, because a
supervisor whose whisper was rejected has to be told — a silent no-op looks
exactly like a whisper the agent ignored.
