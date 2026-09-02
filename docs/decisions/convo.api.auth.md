# `convo.api.auth`

The reasoning that used to live in the docstrings of `convo/api/auth.py`; the code keeps one line per symbol.

## module

Tenant isolation lives in this module, not in the SFU: a LiveKit API key can
sign for any room, so the exact-string room grant minted here is the fence.
The JWT also carries `RoomAgentDispatch(agent_name=FLEET, metadata=SessionMeta)`
— the same JSON `core.router.resolve` reads — so who a session is for is
decided once, at the door, and travels with the room.

`mint_observer` is the second ticket this module signs: the same fence, with
the publish rights removed, so a supervisor can listen to a call in progress
without the caller ever learning that somebody joined. `mint_caller` is the
third: full publish rights into a room that already dispatches its own agent,
which is how a synthetic caller (ring 2) gets in.

`mint_supervisor` is that idea with a role on it. One human, one identity
(`sup:<uid>`), three capabilities, and one grant shape per capability — so
what a supervisor may do in a room is decided here, by the signature on a
token, and not by anything the browser sends afterwards. The tokens are
short-lived by design: a supervisor's ticket outliving the call it was minted
for is a standing key to a room.

Open source note: `mint_session` is a generic recipe for explicit agent
dispatch on livekit-agents 1.7 — a JWT from plain args, no server round-trip;
`mint_supervisor` is the same recipe for role-scoped humans.

## public_url

The worker joins over `LIVEKIT_URL` (loopback on the box, `ws://127.0.0.1:7880`);
a browser cannot use that, so a session token carries `LIVEKIT_PUBLIC_URL`
(`wss://lk.bernardocastro.dev`) when set, and falls back to `LIVEKIT_URL`
for the laptop stack where the two are the same.

## mint_observer

This is how a supervisor listens to a call that is already happening. The
grant is the opposite of a caller's: `can_publish=False` means no
microphone can reach the room from this token however the browser is
driven, and `hidden=True` keeps the observer out of the room's participant
list, so the caller is not told somebody joined. It carries no
`RoomConfiguration`: an observer never dispatches an agent, it joins a room
an agent is already in.

## mint_caller

The third ticket, and the one an eval harness needs. `mint_session` puts
the dispatch inside the JWT, which only works for a client that joins with
the token we minted; DeepEval's `LiveKitConnector` signs its own token and
cannot carry metadata, so an eval room is dispatched server-side
(`core.rooms.create_eval_room`) and the caller is handed this instead.

It therefore carries NO `RoomConfiguration`: the room already dispatches,
and a second dispatch would put two agents in one room, both greeting.

## mint_supervisor

→ `{url, room, identity: "sup:<uid>", capability, token}`

The identity is the trust anchor: the SFU puts it on every packet and RPC
the supervisor sends, the agent gates on it with
`core.security.supervisor.is_supervisor`, and nothing in a payload can
forge it. A signed `{"role": "supervisor", "cap": …}` attribute rides
along so a reader that already trusts the identity can also see which
powers were handed out, without decoding the grants.

The same human keeps the same identity across capabilities on purpose:
LiveKit admits one connection per identity, so swapping a `listen` ticket
for a `takeover` one upgrades the participant already in the room instead
of adding a second ghost of the same person.
