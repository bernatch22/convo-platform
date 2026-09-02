# `infra.scripts.isolation_probe`

The reasoning that used to live in the docstrings of `infra/scripts/isolation_probe.py`; the code keeps one line per symbol.

## module

The warm transfer stands or falls on one primitive: two participants confer
while a third, already in the room and already subscribed, hears nothing. This
puts three peers in a room, has each publish a continuous tone, and counts the
frames each one actually receives while both candidate mechanisms are switched
on and off. A phase is isolated when the counter does not move.

    docker compose -f infra/compose/dev.yml up -d          # a server to ask
    uv run python scripts/isolation_probe.py

Expected, on livekit-server v1.9.1 (this is the measurement `core/telephony/
isolation.py` is built on — 400 frames is 4 s of audio, 0 is silence):

    P0 baseline                     caller <- agent 400   caller <- human 400
      settling                       44 frames still reached the caller
    P1 update_subscriptions(False)  caller <- agent   0   caller <- human   0
      settling                      198 frames (audio resuming, the other way)
    P2 update_subscriptions(True)   caller <- agent 400   caller <- human 400
      settling                       42 frames still reached the caller
    P3 briefing (track perms)       caller <- agent   0   caller <- human   0
      settling                      198 frames (audio resuming)
    P4 bridged (perms re-opened)    caller <- agent 400   caller <- human 400

Both mechanisms cut the audio completely, and both take about the same time to
bite: 44 frames over two streams is ~220 ms per stream. That number is the
warm transfer's one residual — see `core.telephony.transfer.WarmLeg.dial`.

**Count frames, not events.** The first version of this probe watched
`track_subscribed` / `track_unsubscribed` on the participant being cut off and
concluded that neither mechanism worked — while the SFU's own log said
`revoking subscription`. The Python SDK fires no unsubscribe for a server-side
revocation; the `AudioStream` simply goes quiet. The wrong instrument gave a
confident wrong answer, and it would have shipped as "warm is impossible here".

Open source note: this measures a property of the SERVER, not of this project.
Point it at any LiveKit deployment before building a side-channel on top of one.

## settle

This is the number the warm transfer is built around, not a formality: a
cut that takes effect a beat late is a beat of the briefing the caller
hears. It is reported in frames of 10 ms.
