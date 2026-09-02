# `convo.session.sip`

The reasoning that used to live in the docstrings of `convo/session/sip.py`; the code keeps one line per symbol.

## module

A phone call arrives as a **room** job, not a participant job: the dispatch
rule asks for `agent_name` on room creation, so `ctx.job.participant` is empty
and the number the caller dialled lives on the SIP participant inside the room
(`sip.trunkPhoneNumber`, `sip.phoneNumber`, `sip.callID`, `sip.twilio.callSid`).

`livekit-sip` creates the participant and the room together, so the participant
is normally already there when the worker connects; the bounded wait below
exists only for that race and returns immediately in the common case.
