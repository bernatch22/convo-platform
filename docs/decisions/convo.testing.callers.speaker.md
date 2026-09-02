# `convo.testing.callers.speaker`

The reasoning that used to live in the docstrings of `convo/testing/callers/speaker.py`; the code keeps one line per symbol.

## module

A real `--record` run needs a microphone and a room. `RecorderIO` — the thing
that writes the stereo OGG — is only wired by `AgentSession.start` when there
is a job context AND both an audio input and an audio output, which a headless
harness session has neither of. So this file supplies the missing half:

  `VirtualSpeaker`  an `AudioOutput` that "plays" the TTS at wall-clock speed
                    and reports each segment where it finished, so the recorder
                    places the agent's words on the real timeline
  `Recording`       the framework's `RecorderIO`, wired by hand around that
                    speaker and started before the session is

The caller's channel stays SILENT on purpose: no microphone was ever attached
and `record_input` is given an input nobody iterates. The OGG is therefore a
truthful stereo file — L = caller (silence), R = agent — of a call in which the
caller typed. What that costs each voice metric is written down in
`docs/evals.md` §3.9.

`VirtualMicrophone` is the other end, and the one ring 2 needs: a synthetic
caller in a REAL room has to put sound on the wire, so it speaks its line with
a TTS of its own and reports the wall-clock window that line occupied. The two
classes never meet — one is an `AgentSession`'s output, the other a
`rtc.Room`'s input — but they are the same idea twice and belong together.

Open source note: nothing here knows about tenants. Hand `Recording` any
`AgentSession` with a TTS and it hands back the OGG that session would have
produced; hand `VirtualMicrophone` any livekit-agents TTS and it is a headless
caller's mouth in any LiveKit room.

## VirtualSpeaker

Frames arrive from the TTS far faster than they are spoken. A sink that
accepted them and reported "finished" immediately would collapse a
forty-second call into two seconds of OGG and give every turn a latency it
never had, so this one sleeps out the audio it was handed before reporting.

## VirtualMicrophone

The pacing is the SFU's, not ours. `AudioSource.capture_frame` blocks once
its queue is full and `wait_for_playout` returns when the queue has
drained, so pushing every synthesised frame and then waiting takes the same
wall-clock time the sentence takes to say. That matters twice: the agent's
VAD must see the real gap after the line, and the window `say` reports is
what gives the caller's turn an `Audio.start_time` that is true.

The samples are kept as they go out, because a scored turn needs the SOUND
of what the caller said and no track carries our own voice back to us.

`http_session` is not optional plumbing. A livekit-agents plugin asks the
framework's job context for its HTTP session, and a harness that is not a
job has none: without one handed in, the first `say` dies with "Attempted
to use an http session outside of a job context". Whoever passes it owns
nothing — this closes it.

## Recording

Three moments, because `AgentSession.start` clears `_recorder_io` on its way
through: wire the output BEFORE the session starts (or the greeting is
spoken into a sink nobody is recording), `adopt` the recorder after it
started so `session.end` can report where the audio went, and `aclose` it
before the session closes so the file is complete.

## Recording.aclose

The writer only fills the timeline up to `now`, and `now` at close is
the instant the last frame finished playing — which cuts the decay off
the final word and reads to `AudioIntegrityMetric` as an abrupt cutoff.
A beat of silence first is what a real line has anyway.
