# `convo.api.supervise`

The reasoning that used to live in the docstrings of `convo/api/supervise.py`; the code keeps one line per symbol.

## EnteredRequest

Nothing here is trusted beyond "look at this room for this identity". The
capability is read off the participant's signed attributes at the SFU, not
taken from this body — which is why there is no field for it.

## VerbRequest

`identity` is the supervisor the SFU will be asked about; nothing here is
trusted beyond "look at this room for this identity". The agent asks the
same question again of the packet it receives.

`mode` is per-verb and deliberately one field: `inject` / `inject_and_speak`
for a steer, `cold` / `warm` for a transfer. Empty means "this verb's
default", which is the only value that is right for every verb.
