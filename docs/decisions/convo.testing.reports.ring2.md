# `convo.testing.reports.ring2`

The reasoning that used to live in the docstrings of `convo/testing/reports/ring2.py`; the code keeps one line per symbol.

## module

Ring 1 runs the agent in-process with no audio at all; ring 3 scores calls that
already happened. This is the ring in the middle, and the only one where the
whole pipeline is under test at once — Soniox hears a voice it did not
synthesise, the turn detector decides when the caller stopped, Haiku answers,
ElevenLabs speaks, and the answer comes back over WebRTC like any other call.

    from convo.testing.reports.ring2 import converse
    script = await converse(persona, "clinica-norte", "reagendamiento", [
        "Hola, llamo para cambiar mi cita del martes.",
        "El jueves por la mañana me viene bien.",
        "Perfecto, gracias.",
    ])

Three facts shape everything below.

  **The room is minted by `api.py`, never here.** DeepEval's `LiveKitConnector`
  signs its own token and dispatches by `agent_name` with no metadata
  (`voice/connectors/providers/livekit.py:179`), so a room it opens alone
  reaches a worker that cannot tell which tenant called. `POST /evals/rooms`
  dispatches server-side with the same `SessionMeta` a web token carries and
  hands back a ticket into a room the agent is already joining. That is a
  verified limitation of the connector, not a preference.

  **Latency is measured on the wire, and it is not `e2e_latency`.** It is the
  moment the agent took the floor minus the moment the caller stopped talking,
  so it includes the SFU and the agent's own endpointing: it is larger than the
  `ChatMessage.metrics.e2e_latency` ring 3 reads off the same call, and the two
  are never compared.

  **Every turn carries `Audio` with a `start_time`.** The agent's is cut from
  the timeline the call writes as frames arrive; the caller's is the samples
  the microphone actually sent, since no track carries our own voice back to
  us. `TurnTakingNaturalnessMetric` rebuilds the call from those offsets and
  scores nothing without them.

The room mechanics — joining, the microphone, the two transcription streams,
the agent's own clock — are `core.testing.caller.Call`, which is where the
first two facts are made true; this module is the door and the result.

Open source note: nothing here knows a tenant. Point `converse` at any control
plane that mints `{url, room, token}` for an already-dispatched room, and this
plus `caller.py` is a headless LiveKit voice client.

## Transcript

The turns are DeepEval's own `Turn`, audio and latency included, so a suite
scores this object directly — `case()` is only the envelope a
conversational metric wants around them.

## converse

The agent greets first, so the transcript opens with an assistant turn
whose latency is how long the greeting took to arrive. Each line after that
is spoken in real time, answered, and — if the persona is patient — waited
out; a persona with a `patience_s` talks over the answer instead, and the
turn it cut off is settled while its own line is still going out.

The caller's turn is built AFTER its answer arrives, never before: the STT
transcript of a line lands a moment after the line ends, and a turn built
on the instant we stopped talking would carry no transcript at all. That
holds for an impatient caller too — the agent only takes the floor once it
has decided our turn ended, so by then its transcript of us is published.

## session_of

It has to be asked DURING the call: `/live-calls` matches rooms the SFU
still holds against sessions that are still open, and the moment we hang up
the agent leaves and the room is gone. What it buys is the half of a call
the caller cannot hear — a synthetic caller sees what was SAID, and the
consent policy is about what the platform DID, which only the event log
knows.

A control plane that cannot answer is not a failed call: the transcript is
still a transcript, so this returns None rather than raising.

## microphone

The `aiohttp` session is built here and handed to the plugin. A harness is
not a job, so there is no job context to borrow one from — see
`VirtualMicrophone`, which closes it when the call hangs up.

`language` is left UNSET for a caller who code-switches. Pinned to "es",
ElevenLabs reads "where is my package" with Spanish phonemes, and what
arrives at the STT is then a Spanish accent doing English rather than
English — which would make the transcript prove nothing about
`language_hints` either way.
