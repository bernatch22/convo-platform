# `convo.testing.callers.personas`

The reasoning that used to live in the docstrings of `convo/testing/callers/personas.py`; the code keeps one line per symbol.

## module

A persona here is **data**, not a subclass. Three of them were drafted and two
survived, because a persona only earns its place if it breaks something the
others cannot reach:

  `APURADO`   cuts the agent off. He is the only way to put barge-in, the turn
              detector and the framework's interruption path under a real
              microphone: everything else in the suite politely waits for
              silence, which is the one thing a real caller never does.
  `SPANGLISH` switches es↔en inside a sentence. She is the only caller whose
              transcript can prove `language_hints` is doing something — a
              Spanish-only STT does not fail loudly on English, it quietly
              writes down the nearest Spanish words.

What a persona owns and what a golden owns is a line worth keeping straight.
The persona is WHO is calling: a voice, a way of speaking, and a patience. The
golden is WHAT they want and what has to hold while they get it — and its
`turns` are the script, written in that persona's own words, which is the only
"script strategy" this ring needs while `converse` takes fixed lines. When the
simulator writes the lines instead (ring 2's next step), `card()` is what it is
handed: the same persona, in DeepEval's own vocabulary.

`patience_s` is the whole of the interruption model, and it is deliberately one
number: how many seconds of the agent's answer this caller will sit through
before talking over it. `None` means "hears the answer out", which is every
caller the platform has ever been tested with until now.

Open source note: nothing below knows a tenant. A `CallerPersona` is a voice
id, a prompt and a patience — hand it to `core.testing.ring2.converse` against
any project, or to DeepEval's simulator via `card()`.

## CallerPersona

`language` is the TTS's, not the caller's country: it is left unset for a
caller who code-switches so ElevenLabs reads each line in the language it
is actually written in. `multilingual` says the same thing to the STT side
of a DeepEval simulation, and to the suite that asserts both languages came
back transcribed.

## CallerPersona.card

`interruption_behavior` is what DeepEval's own duplex path reads and
our transport does not: we cut in on `patience_s` ourselves, because
`converse` speaks a written script rather than a generated one. Setting
it anyway costs nothing and keeps the two descriptions of this caller
from drifting apart the day the simulator writes the lines.
