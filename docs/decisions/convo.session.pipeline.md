# `convo.session.pipeline`

The reasoning that used to live in the docstrings of `convo/session/pipeline.py`; the code keeps one line per symbol.

## module

Nobody should have to read `convo/providers/*.py` to know which Soniox model
answers a call, whether the prompt is cached, or which voice speaks. This
module turns those constants — plus the project's own voice, model and
greeting, and the latencies its last calls actually measured — into one dict
the console renders and a test can assert on.

It is a READ of the platform's own configuration: every value here is either a
constant from `convo.providers`, project data, a row of the store, or a median
over stored events. Nothing is invented and nothing is defaulted silently — a
project that has never run answers with `null` medians, never with a zero, and
a project nobody can phone says so instead of borrowing the fleet's number
(`convo.telephony.lines`).

The write half is `overridable`: the fields the console may set, and the rules
that refuse a value the platform will not run.

## stt_view

`endpointing` is the chosen provider's own dial set, not a common
denominator: Soniox holds a turn open for a silence window, Flux scores its
belief that the sentence closed. Flattening the two into shared keys would
invent a knob neither provider has, so the console branches on `provider`.

## llm_view

`requested_model` is what the project asked for and `model` is what runs.
They differ for two reasons: git names a model outside `ALLOWED_MODELS`,
which `llm_model()` falls back on rather than opening a connection nobody
priced, or this host carries no key for the vendor, which it falls back on
rather than dying mid-job. `unavailable_reasons` is the second case said in
the server's own words — the very sentence a PUT would be refused with —
so the console greys a model out before somebody chooses it.

## tts_view

`forbidden_reasons` carries the very sentence `overridable` would answer a
PUT with, so the console can grey a model out and say why in the server's
words instead of keeping its own copy of the rule.

## latency

Medians, not averages: one 9-second turn where a tool waited on a slow
adapter says nothing about what the caller usually hears. `null` means the
turns carry no such measurement — a text session has no `tts_node_ttfb`,
and a project nobody has called has nothing at all.

## running

Written onto `session.start` so a call can be traced back to the voice it
spoke with: the console may change any of these between two calls, and
without them on the log there is no artefact tying a supervisor's pick to
what the caller heard. A chat session builds neither STT nor TTS
(`convo.session.build.build_session` gates both on the channel), so the audio half
is null there rather than a voice nobody was ever spoken to in.

## cleaned

A pasted voice id arrives with a trailing space often enough to matter, and
a value that is only whitespace has to reach `overridable` as the empty
string it is, or the refusal below never fires.

## overridable

Five rules about the value, and one about the box.

The box one is the youngest and it was bought at full price: on 2026-08-31
the console stored `llm_model=gpt-5.4-mini` — legal, priced, on the
allow-list — onto a host with no `OPENAI_API_KEY`, and every job of that
project died building its LLM until somebody went and read a worker log.
`convo/api/app.py` runs ON the box the worker runs on, so the one question a console
somewhere else cannot answer, this function can: is the key here? A
provider slot the host cannot open is refused with the variable that would
have to exist, never with anything read out of it. The worker no longer
crashes either (`llm_model`, `provider_for`), but that is the net, not the
door: an operator who asks for an ear the box cannot open deserves the
answer now, not a project quietly running on the other one.

The five value rules. The voice one exists because an empty id is not refused
anywhere downstream — it is *absorbed*: `tts_for` reads it as "no voice
configured", builds no TTS, and the call is silent with a log line blaming
a missing API key. A rule that only the store can enforce belongs here.
The TTS one the platform has always enforced: `eleven_v3` is not
realtime and `eleven_turbo_v2_5` is deprecated, so neither may be stored —
`tts_model()` would silently ignore them at build time and the console would
show a model the caller never hears. The LLM one is an allow-list rather
than a deny-list: a model the platform runs is one somebody priced and
measured, so "may I run X" is no unless X is one of the two, and the
refusal names them both. The STT one is the same shape: only the providers
in `convo.providers.stt.PROVIDERS` have a factory, so any other name would
fall back to Soniox and the console would show an ear the caller is not on.
The transfer one is the youngest of the five and the only one whose EMPTY
value is legal: clearing `transfer_number` is how a console takes the
handover verb away from the agent, and anything else has to be a number a
SIP REFER can carry (`convo.telephony.human.refusal`).

## _absent

`fallback` is what the worker would run instead, and None when the value IS
the platform default: there is nothing under it, so the sentence has to ask
for the variable rather than offer an alternative.
