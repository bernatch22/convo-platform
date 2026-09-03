# `convo.adapters.human`

The reasoning that used to live in the docstrings of `convo/adapters/human.py`; the code keeps one line per symbol.

## module

Every other adapter in this codebase belongs to a tenant — an agenda, an order
book, an SMS gateway. This one belongs to the platform, and it is an adapter
rather than a special case in the executor for one reason: a transfer is a
WRITE, and everything the platform promises about a write must apply to it. The
catalog says whether the project may call it, `guard.check` vets it, the
timeout is the spec's, the failure sentence is the project's, and both halves
of the attempt land in the session log — `tool.call`/`tool.result` like any
other tool, and one `supervisor.transfer` line carrying the mode and the
outcome, the same vocabulary a supervisor's transfer writes (ms-15).

It is attached to every context by `convo.tools.executor.attach_local_tools`, next to the
tenant's own adapters, and it is reachable only by a project that declares
`transfer_to_human` in its catalog. A project that does not is exactly where it
was before this file existed.

The one judgement it makes is what kind of call this is, and each kind gets
the honest mechanism. A PSTN caller has a SIP leg, so a REFER moves it to the
colleague. A browser caller has none — so the phone comes to THEM: a warm
bridge dials the colleague INTO the room (`Handover.join`), refused at the
door when the box has no outbound trunk. A chat has no audio to join at all,
so it keeps the refusal it always had. Every branch writes the attempt down,
and the two refusals never touch the SFU.

## HumanTransfer.execute

→ the `Outcome` payload (`mode`, `outcome`, `to`, `ok`, …), which
`convo.agents.human` turns into the sentence the model acts on. `ok=False`
is an ANSWER and not an exception: the caller is still on the line and
somebody has to speak to them.

`ToolError` is raised for the cases where nothing was even attempted —
no number, no call to move, a warm bridge this box cannot dial — because
the model must read those as "this did not happen" and not as a
transfer that failed.

## HumanTransfer._join

`TransferRefused` here is the door doing its job — on this box almost
always "no `SIP_OUTBOUND_TRUNK_ID`" — so the refusal is logged with the
sentence that names the variable, nobody's phone has rung, and the
model reads an honest "this cannot be done right now".

## HumanTransfer._fall_silent

The same `takeover` a supervisor's warm transfer ends in
(`convo.supervision.control`), so the audit shows the mute and a later
`release` from the desk could hand the line back the same way.

## HumanTransfer._handover

The room and the session hang on `SupervisorControl`, built in
`convo/worker.py` with the job's own room — the same two things a supervisor's
transfer uses, read from the same place, so an agent-initiated transfer
and a desk-initiated one cannot disagree about which call they are
moving. A console run and the eval harness have no control at all, which
is the honest answer that they have no call to move either.
