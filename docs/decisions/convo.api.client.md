# `convo.api.client`

The reasoning that used to live in the docstrings of `convo/api/client.py`; the code keeps one line per symbol.

## module

`api.py` is the door; this is what is behind it. Every function here takes a
`Store` and returns plain dicts — no FastAPI, no SQL above the store, no
knowledge of who is asking — so the same views feed the HTTP endpoints, a
test, and one day a Postgres deploy without a line changing.

The job process never calls this in production: it talks HTTP to `api.py` and
the control plane is the only thing holding a database handle.

`live` is the same read as `session`, one poll at a time: an SSE stream over
the store with a `seq` cursor. A session's log is append-only and numbered, so
"what is new" is a comparison, never a subscription — a client that vanishes
costs nothing and a client that reconnects says which seq it had.

## live

Three event names reach the browser: `open` once (the row, so a client that
joined late can label the screen), `append` per log line, and `end` when
`session.end` lands — after which the stream closes itself. A comment line
goes out every `KEEPALIVE_S` of silence so a proxy does not reap an idle
call that is merely listening.

## live_calls

Two matches are possible and neither is a join the database could do. A web
room is named `<tenant>-<project>-<hex>` by `mint_session`, so its prefix
names the project. A phone room is named by the dispatch rule, so the only
honest key is the number: the caller's `sip.*` attributes are on the room
AND on the session's first event. Nothing matched leaves `session_id` null
— a call the console can watch but not yet read.

## _match

An eval room is named `eval-<tenant>-<project>-<hex>`, so the prefix that
names its project is one word further in. Ring 2 asks this question of
itself mid-call — a synthetic caller hears what was said and needs the log
to know what was done — and a console that showed a synthetic call as
unreadable would be wrong for the same reason.

## _phone_of

Only `session.start` carries the SIP attributes, so this reads the first
event and stops. A null answer is the honest way to say "this session never
came in over the telephone" — it is what makes a phone row distinguishable
from a browser one in the call log, where nothing else would tell them apart.

## _row_view

`audio` is a look on disk and not a look in the log on purpose: the log
says where the OGG was AIMED, the disk says whether there is anything to
play. A killed job, a chat session and a project that opted out all
answer false, and the console needs no third state to draw a player.
