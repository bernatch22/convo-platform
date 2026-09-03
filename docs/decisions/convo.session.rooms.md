# `convo.session.rooms`

The reasoning that used to live in the docstrings of `convo/session/rooms.py`; the code keeps one line per symbol.

## module

The store knows what a session DID; only LiveKit knows what is on the wire
this second, and an inbound phone call never passed through `/token` — the
trunk dispatched it. So the console's "somebody is on the phone" light cannot
come from the database: it comes from `RoomService.list_rooms`, filtered to
the rooms an agent actually joined.

The server is a dependency this process does not control. Every failure —
unreachable, wrong key, no `LIVEKIT_URL` — arrives as `RoomsUnreachable` so
the door can answer 503 and the console can say "the SFU is down" instead of
"there are no calls", which is a different and much worse sentence.

`create_eval_room` is the write side, and the only one: a room dispatched
server-side, with metadata, for a caller that cannot carry any — see its
docstring for why that caller exists.

## create_eval_room

The one door ring 2 enters through, and the reason it exists is a
limitation nobody can code around: DeepEval's `LiveKitConnector` signs its
own join token and dispatches with `RoomAgentDispatch(agent_name=…)` and
**no metadata** (`voice/connectors/providers/livekit.py:179`), so a room it
opens on its own reaches an agent that cannot tell which tenant called.
Dispatching from here instead puts the same `SessionMeta` JSON a web token
carries into `ctx.job.metadata`, where `convo.session.router.resolve` already reads
it — the harness then joins a room whose agent is already on its way.

The name is prefixed `eval-` so a synthetic call is one glance apart from a
real one in `/live-calls` and in the SFU's own logs. `persona`, when the
caller names one, rides on the dispatch attributes as `eval.persona`: the
worker's job then says which persona is calling it.

Explicit dispatch creates the room if it does not exist, so this is one
round-trip, not two.

## client

`livekit.api.LiveKitAPI()` reads the environment itself and raises when `LIVEKIT_URL`
is unset — which on a laptop running the dev compose is not "unconfigured",
it is "the defaults". `convo.api.auth.mint_session` has always fallen back to
`ws://localhost:7880` + devkey/secret, and a console that can hand out a
token for a room it then cannot list is the wrong kind of surprising. A key
that is wrong for the server still arrives as `RoomsUnreachable`.
