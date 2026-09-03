# `convo.providers.stt`

The reasoning that used to live in the docstrings of `convo/providers/stt.py`; the code keeps one line per symbol.

## module

Which one hears the caller is project data (`Project.stt_provider`), like the
voice is — so a supervisor switches ear from the console and the next call
runs on it, no deploy. This module is the dispatch and the two tunings; every
value below is a constant a test can assert on without a network.

Soniox `stt-rt-v5` decides where an utterance ends from the words themselves,
not from silence alone; its three endpoint knobs are the voice-agent profile
(the API defaults are 0 / 0.0 / 2000 ms and about half a second slower).
`context.terms` is the one vocabulary channel the model reads (`keyterms` is
silently ignored), so a project's own words go there.

Deepgram Flux talks a different websocket (`/v2/listen`, the plugin's `STTv2`)
and folds end-of-turn detection into the transcription model itself: instead of
a silence window it emits a turn when it believes the sentence closed, scored
against `eot_threshold`. `flux-general-multi` is the member of the family that
speaks Spanish — `flux-general-en` is English-only and answers a `language_hint`
with a 400 — and Flux takes its vocabulary as `keyterm`, the argument Soniox
ignores.

Either ear needs its own key on the box that runs it, and a console that sets
`stt_provider` may be pointing at a fleet that does not carry it. `KEY_ENV_FOR`
names where each key lives and `runnable` asks whether this host has it: the
control plane refuses such an override at the door, and `provider_for` treats
one already stored as unusable config and falls back, so a switched ear can
never leave a project deaf. Only the variable NAME is ever printed.

The turn detector in `convo.providers.turn` is the second opinion either way;
the session combines both.

## provider_for

Same rule as `convo.providers.tts.tts_model`: unusable data falls back to the
platform default instead of failing a call, and a key this box does not
carry makes the choice unusable exactly as an unknown name does. Soniox is
the floor — when its own key is absent too, `soniox_stt` answers None and
the session is text-only, which is what it has always done.

The control plane refuses both at the door (`convo.session.pipeline.overridable`):
an unknown provider, and one whose key is missing from the host it would
run on. This is the second line, for an override stored before the key
went away.

## deepgram_options

`STTv2` has no options object of its own the caller can hand it (its
`STTOptions` carries the endpoint url too), so the tuning travels as this
dict and both the factory and the console read the same one.

## _warn_if_swapped

Only the keyless case earns a line: a provider name nobody recognises is a
deploy-time mistake the console already shows, while a key absent from THIS
box is an operational fact nobody can see from there.
