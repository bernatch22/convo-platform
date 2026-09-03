# `convo.telephony.transfer`

The reasoning that used to live in the docstrings of `convo/telephony/transfer.py`; the code keeps one line per symbol.

## module

**Cold** is one API call. `TransferSIPParticipant` makes `livekit-sip` send a
SIP REFER on the caller's own leg; the carrier takes the call from there, the
caller leaves the room and this job ends. It is the whole of a blind transfer
and it needs nothing but a trunk that accepts REFER.

**Warm** is hand-rolled, and it is hand-rolled for a reason that was measured
rather than read: `MoveParticipant` — the RPC the framework's own
`WarmTransferTask` is built on — answers `twirp error unknown: not
implemented` on this server, so the supported path does not exist here. What
does exist is `CreateSIPParticipant`, which dials a phone INTO the caller's
room, and `convo.telephony.isolation`, which makes the briefing inaudible to
the caller while it happens. Those two are enough.

**A failed transfer must leave the caller where they were.** That is the
difference between an outcome and an accident, and it is why every failure
below comes back as an `Outcome` with `ok=False` and a SIP status rather than
an exception: the agent has to say something to somebody who is still on the
line. `SipCallError.sip_status_code` is what makes that sentence specific — a
486 is "he is on another call", a 603 on this trunk is very nearly always "the
carrier refused the REFER", which is a deployment fault and not the caller's.

What warm needs and this deployment does not yet have: an **outbound**
(termination) trunk. `infra/box/README.md` says it plainly — the box's Twilio
trunk has Origination and no Termination, so there is no id to put in
`SIP_OUTBOUND_TRUNK_ID` and dialling out is refused at the door with
`TransferRefused` instead of failing halfway through a call. Creating that
trunk is a deliberate, human, out-of-band act (see the fraud checklist), not
something this module does on the fly.

Open source note: the whole file is tenant-free and framework-free — it talks
to `livekit.api` and nothing else. A stranger gets cold and warm transfer for
any self-hosted LiveKit SIP deployment by copying this and `isolation.py`.

## cold

→ an `Outcome`. `ok=False` always means the caller is STILL IN THE ROOM,
which is the only reason this returns instead of raising: somebody is
waiting to be spoken to.

## WarmLeg

Three moves, in this order and only this order: `dial` brings the human in
with the caller already cut off, `bridge` opens the three-way, and
`hang_up` undoes everything when the briefing decides against the transfer.
Each returns an `Outcome`, and a failed `dial` has already restored the
caller's audio before it returns.

## WarmLeg.dial

`silenced` is what the choreography cut BEFORE dialling — the agent's
own track — so that a failure here can put it all back in one place.

## destination

The number is deployment data, not the platform's: a desk that names one wins, and
the env var exists so the demo has a mobile to ring without one.

## phone_number

`CreateSIPParticipant` takes a number, not a URI: a SIP destination needs
`sip_request_uri` and a trunk configured for it, which is a different
deployment and not something to guess at mid-call.
