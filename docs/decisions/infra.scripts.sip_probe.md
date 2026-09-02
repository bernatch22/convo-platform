# `infra.scripts.sip_probe`

The reasoning that used to live in the docstrings of `infra/scripts/sip_probe.py`; the code keeps one line per symbol.

## module

Everything between the carrier and the agent can be tested from a laptop: this
sends the INVITE Twilio would send and reads what comes back. A `200 OK` means
`livekit-sip` matched the number against a `SIPInboundTrunk`, the dispatch rule
opened a `call-…` room and the fleet was dispatched; the worker's log then shows
which tenant `store.route` resolved. Only the audio is not exercised — no RTP is
sent, so the agent greets an empty line and hangs up when we send BYE.

    uv run python scripts/sip_probe.py                       # the wired number
    uv run python scripts/sip_probe.py --dialled +34910000000 --hold 20

The box's allow-list will refuse you. `SIPInboundTrunk.allowed_addresses` holds
Twilio's signalling ranges, so an INVITE from a laptop is dropped with no reply
at all — the same silence a misconfigured trunk gives. Add your address for the
run and take it out afterwards (`curl -s https://api.ipify.org` for the value):

    lk.sip.update_inbound_trunk_fields(trunk_id, allowed_addresses=[*TWILIO, mine])

Open source note: a dependency-free SIP UAC in 120 lines. Point it at any SIP
server to find out whether an INVITE for a number is admitted or dropped.
