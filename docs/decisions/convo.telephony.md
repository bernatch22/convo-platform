# `convo.telephony`

The reasoning that used to live in the docstrings of `convo/telephony/__init__.py`; the code keeps one line per symbol.

## module

`lines` is the origin side — which number reaches which project, read from the
same `routes` table `convo/session/router.py` resolves an inbound call with, so the
console can never claim a line a caller would not actually land on.

`transfer` holds the two LiveKit SIP moves — a cold REFER that hands the
caller's leg to the carrier, and a warm leg that dials a human INTO the room —
and `isolation` holds the one primitive the warm path needs and the SFU is the
only thing that can provide: making one participant inaudible to another
without their client's cooperation. `handover` is the choreography: what the
caller hears, what the human hears, and what the log ends up saying.

Nothing here imports `tenants/`, and nothing here decides WHO may transfer:
that gate is `convo.supervision.control.SupervisorControl.apply`, one door for
every supervision verb.
