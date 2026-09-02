# `convo.session.stt_gate`

The reasoning that used to live in the docstrings of `convo/session/stt_gate.py`; the code keeps one line per symbol.

## module

A streaming STT is a language model with a microphone, and over a silent line
it does what language models do — it invents. On the human's call
AJ_rt86KogpPxDa Soniox emitted a final `"Thank you."` (language `en`,
transcription delay 3.32 s) while nobody had said a word yet; the framework
committed a user turn for it, the greeting was interrupted, and the agent
answered "De nada" to a phantom. The same happens to every streaming provider
over PSTN comfort noise, and the invented sentence is different every time, so
a blocklist of hallucinated phrases is not a fix, it is a diary.

What is always true is that a transcript with no voiced audio behind it is not
something the caller said. This module measures that, on the very frames going
into the STT, and refuses the transcript when it finds nothing:

    accept a transcript  ⟺  the last `max_lag_s` seconds of audio carried at
                            least `min_voiced_ms` above the line's noise floor

Why it is measured here and not by the session's VAD: the VAD is a second
consumer of the same audio, its decisions are private to
`AgentActivity._audio_recognition`, and by the time it disagrees with the STT
the turn is already committed. `Agent.stt_node` is the one seam the framework
offers where a transcript can still be dropped before anything downstream —
the interruption, the chat context, the reply — has seen it. `TenantAgent`
wires it; this module holds the arithmetic and knows nothing about tenants.

Voiced is decided against the LINE's own noise floor, not an absolute level: a
Twilio leg, a laptop microphone and a WebRTC browser sit 20 dB apart, and the
one thing they share is that speech is far above whatever the line hums at.
The floor falls fast and rises slowly (speech must not lift it) and the
threshold it produces is clamped into a band, so the gate can never demand more
than `MAX_SPEECH_DB` of a quiet caller nor accept hiss on a dead line.

Open source note: `TranscriptGate` takes audio frames and speech events and
returns booleans. Nothing here knows about tenants, LiveKit rooms or Soniox.

## GateOptions

`min_voiced_ms` is a fraction of one syllable: any word a caller actually
says clears it, and comfort noise never does. `max_lag_s` is the window
that audio is looked for in, sized at twice the worst transcription lag we
tune Soniox for (`max_endpoint_delay_ms=1000`), so a slow final for real
speech is still inside it and the 3.32 s phantom is not.

## gate_options_for

Data, like `Project.backchannels`: a tenant on a noisy analogue trunk raises
`margin_db` from the console without a deploy, and a tenant that wants the
old behaviour back sets `min_voiced_ms` to 0. Unknown keys are ignored
rather than raising — this sits in the audio path of a live call.

## TranscriptGate

One instance per STT stream, i.e. one per `stt_node` call. `hear` wraps the
frames on their way in, `accepts` judges each event on its way out, and
`dropped` counts what it refused so a session report can say so.

## TranscriptGate.measure

The frame is classified against the floor as it stands, and only then
does it move the floor. Doing it the other way round lets a loud frame
raise the bar it is about to be measured against.

## TranscriptGate.accepts

Only transcripts carrying text are judged. Everything else the STT
emits — start and end of speech, usage, an empty final — is the
framework's business and passes through untouched.
