# `convo.testing.callers.caller`

The reasoning that used to live in the docstrings of `convo/testing/callers/caller.py`; the code keeps one line per symbol.

## module

`convo.testing.reports.ring2` decides what a call is FOR — which project, which lines,
what comes back. This is the room mechanics underneath it: connect, publish a
microphone, read `lk.transcription`, watch `lk.agent.state`, write the agent's
frames onto a timeline, hang up. Nothing here knows a tenant or a golden, and
the ticket it is handed could come from any control plane.

Two rules the code follows and the room enforces.

  **Both speakers arrive on one topic, told apart by identity.** In a voice
  session the framework publishes the CALLER's STT transcript under the
  caller's identity (`room_io.py:145`, `is_delta_stream=False`) and the agent's
  under its own (`:153`, `is_delta_stream=True`). The user's interims re-open a
  stream carrying the same `lk.segment_id`, so a segment's text is the text of
  the LAST stream bearing that id — one real turn arrives as a dozen streams
  and one entry. The agent's ids are unique and the rule costs it nothing.

  **`lk.agent.state` is the clock.** The instant that attribute turns
  `speaking` is the instant sound leaves for us, and the instant it turns to
  anything else is the instant it stops. Both the latency of an answer and the
  window its audio occupies are read off those transitions, never off when a
  transcript happened to arrive.

And one thing a caller may choose to do: `listen(since, patience=…)` hands the
floor back after that many seconds of the agent's speech instead of waiting for
silence, so the next line goes out over the top of it. That is the only real
barge-in in the suite — everything else waits politely, which no caller does —
and it costs one extra step per turn: `settle` folds the text of the answer we
cut off into the turn it was cut from, because closing a stream mid-sentence
delivers its words a moment AFTER the interruption.

## Call.listen

`patience` is the persona's, in seconds of the agent's own speech, and
it changes what a turn IS: with no patience the answer is what was said
between two silences, and with one it is what had been said when the
caller decided to talk over it. The second is not a degraded first — it
is the only way a written script produces a real barge-in.

## Call.settle

Interrupting closes the agent's transcription stream, so the words it
HAD got out arrive a moment after we started talking over it. Left in
the inbox that segment would be waiting when the next answer is
listened for, and one turn's words would be read as the next one's.
Call it while our own line is still going out; a turn nobody
interrupted is returned untouched and costs nothing.

## Call._hear_out

A turn that calls a tool speaks twice — "un momento, le consulto" and
then the answer — so one segment is not an answer: the reply ends when
nothing new has arrived for `QUIET_AFTER_REPLY_S`.

Silence on the transcript is not silence on the wire, and reading only
the first was a bug worth a paragraph. The agent's transcription is a
DELTA stream: it closes when the LLM has finished generating, while the
TTS is still several seconds from finishing saying it. A caller who
waited three quiet seconds and then spoke was therefore interrupting a
patient conversation every single turn — the transcripts of a whole run
ended mid-word ("el de 74,90"), which reads as the model trailing off
and is in fact us talking over it. So the floor is what settles it:
`lk.agent.state` says whether sound is still leaving, and only when
both are quiet is the answer over.

## Call._cut_in

The clock starts when the agent TAKES the floor, not when we stopped
talking: a caller who is impatient with answers is not impatient with
the pause before them, and measuring from the wrong end would make the
interruption arrive earlier the slower the agent is.

The text usually arrives after the deadline rather than before it — the
agent's transcription is a delta stream that closes when its speech
does — so a cut-off turn is normally returned empty and filled in by
`settle` a second later. `interrupted` says which of the two happened:
it is true only if the agent still had the floor when we took it.

## Call._floor_taken

`lk.agent.state` arrives as a participant attribute, not as a stream
anything can await, so this is a poll — 20 ms, which is under half a
frame and far under any latency it is used to measure.
