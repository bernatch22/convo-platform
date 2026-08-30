# ms-6 — local voice: talk to the agent from the laptop microphone

**Landed 2026-08-30 · 3 cards (1 by the orchestrator, 2 by Opus workers) · lands on master with this milestone**

## What we set out to do

Put a voice on the process without a server: Soniox for speech-to-text with
its own semantic endpointing, ElevenLabs Carolina for speech, Silero VAD and
the local turn detector on CPU, all chosen by the providers package from the
project's data, and `python worker.py console` in audio mode so the human
talks to the receptionist from the laptop. The log had to keep telling the
story — final transcripts, timed words, latencies, the recording — and the
first voice-shaped evaluation had to run offline on a `--record` session.

## What we achieved

- **`uv run python worker.py console --record`** talks. Soniox
  `stt-rt-v5` (es/en, endpoint sensitivity 0.3, latency level 2, 1000 ms max
  delay, the project's keyterms as context), ElevenLabs
  `eleven_v3_conversational` with the project's voice and `sync_alignment`,
  Silero VAD at 250 ms, the `v1-mini` turn detector locally; `Ctrl+T` toggles
  text and audio. Measured on a real boot: `llm_ttft 945 ms`, `tts_ttfb
  418 ms`.
- **Providers are data before they are connections.** `core/providers/{llm,
  stt,tts,turn}.py`: one factory per capability, every option asserted by a
  test with no network; a project may opt into the `eleven_flash_v2_5` latency
  profile, and `eleven_turbo_v2_5` / `eleven_v3` are never chosen even when
  asked. Without the STT/TTS keys the session is text-only and the console
  still works.
- **Two shapes of session, one builder.** With STT + TTS + VAD,
  `build_session` wires the local turn detector, 0.3/2.5 s endpointing,
  two-word interruptions with false-interruption resume, one preemptive retry
  and the aligned transcript; without them, text only. Observers are wired in
  the same place.
- **The log hears the voice.** `tts.word` per sentence with word times,
  `stt.final`, `interruption.false`, `speech.overlap`, `turn.backchannel`;
  `session.end` carries the OGG path when recording. `convo sessions show`
  renders `Buenos@0.30 días,@0.11 le@0.21 …`.
- **Barge-in tuned for Spanish.** `InterruptionOptions(min_words=2)` is the
  gate that keeps a "vale" from cutting the agent; a project-owned stoplist
  (`Project.backchannels`) catches multi-word murmurs ("vale vale", "sí sí",
  "de acuerdo") — only while the agent holds the floor, because "vale" alone
  *is* a yes when nobody is talking.
- **A recorded call, cut by turn and scored — with no microphone.**
  `core/testing/speaker.py` plays the TTS at wall-clock speed into the
  framework's own recorder; `python -m core.testing.record` produced a 57 s
  stereo OGG of a full booking (Carolina on the right channel, the typed
  caller silent on the left). `core/testing/audio.py` cuts it back into turns
  and `convo sessions eval <id> --voice` scores it: consent 1.0, grounding
  1.0, **Agent Responsiveness 1.0**, Audio Integrity 0.00 — and the zero is
  the metric's, not the audio's (see lesson 8). Answer latency (caller's line
  → agent's first sound) **p50 1.98 s**.
- **The TTS golden, measured honestly.** "Su DNI 12345678Z… 74,90 euros… a
  las 11:30" against a control with the numbers written out in words:
  `eleven_v3_conversational` reads 105 % of the control's duration, flash
  126 % — neither swallowed a token. TTFB cold 0.976 s vs 0.844 s; ~0.44 s
  both on a warm socket. All four WAVs are in the HTML for the human ear.

## What we learned the hard way

1. **`StopResponse` cannot un-interrupt.** LiveKit cuts the agent's audio in
   `_cancel_speech_pause(interrupt=True)` *before* `on_user_turn_completed`
   runs, so a stoplist there cancels the reply, never the interruption.
   `InterruptionOptions.min_words` is the only hook that runs first. Upstream
   has a content-aware backchannel gate, but it is fenced to realtime models
   with no STT — with Soniox + Haiku it can never fire. Generalising it to the
   STT path is the contribution to send upstream.
2. **`tts.word` times are not a session timeline.** The ElevenLabs plugin
   builds `end_time` from per-websocket-message alignment and the framework
   never rebases it. The event's own `t_ms` is on the session timeline; `t1`
   is word duration inside a sentence. Anything that aligns audio to the log
   aligns by `t_ms`.
3. **One `tts.word` event per sentence, not per word.** ElevenLabs streams a
   sentence's alignment faster than it is spoken; per-word appends were a
   ~12/s burst of synchronous SQLite writes sitting in the audio path.
4. **The adaptive interruption detector needs LiveKit Cloud.**
   `AdaptiveInterruptionDetector` wants `LIVEKIT_API_KEY`; on a laptop it
   fails and the session falls back to VAD interruption. `speech.overlap` will
   not fire locally — the observer is right, the model is absent.
5. **`console --record` did not reach `session.start`.** The flag exists
   upstream but recording defaults to the server's `job.enable_recording`,
   which a laptop has no server to ask. `worker.recording()` reads the flag
   (or `RECORD=1`) and passes `record=True` itself.
6. **The plan's `--tenant` and `Ctrl+B` were both wrong.** No custom click
   options; the toggle is `Ctrl+T`. Verified in `cli/_legacy.py`.
7. **A session with no event loop.** `AgentSession()` raises "no current
   event loop" in a sync test — but only when it runs before any async test
   opened one. Every test that builds a session is `async def`.
8. **DeepEval's voice metrics are DSP, not judges** (`evaluation_model =
   None`) — zero model cost. But the dropout detector counts every 20-200 ms
   silence surrounded by speech at a fixed RMS threshold: on a one-phrase clip
   that is a glitch, on a 5-12 s conversational turn those are the pauses
   between words, and three exhaust the penalty. Clean audio, uncalibrated
   metric; the test asserts the defect breakdown, never the score. The
   upstream fix (scale the threshold with the clip) is written down.
9. **The alignment returns the input text.** ElevenLabs' normalizedAlignment
   for Spanish comes back with digits unexpanded, so it cannot prove how a
   number was spoken — hence the duration A/B against a spelled-out control.
10. **A turn's log time is its END.** `turn.agent` is written when the item
   commits, after its audio played; the start is the last `state → speaking`,
   and the new `audio.start` event ties the log clock to sample 0 of the OGG.
11. **A typed caller has no `stt.final` and no framework `e2e_latency`** —
   both are measured from an end of utterance a typed turn does not have.
   The report says `answer` instead and names the gap; the microphone run
   (`console --record`) is the one that has the other half.

## Decisions

- **Voice is project data.** `Project.voice`, `Project.tts_model`,
  `Project.keyterms`, `Project.backchannels`; nothing in core names a voice.
- **No GPU, no downloads.** Silero is the native binary in
  `livekit-local-inference`; the turn detector is the local `v1-mini` with
  `local_fallback=True`; sample rate stays 16 kHz even on PSTN.
- **`min_words=2` first, stoplist second.** The word count is the only
  filter that runs before the interruption; the stoplist is a second net.
- **Interims never enter the log.** `stt.final` only; a test guards it.

## Where we stand

Voice is on master: the same worker that answers two businesses in text now
listens and speaks on a laptop, records itself, writes every word it spoke
with its time into the append-only log, and a recorded call is scored by the
same consent and grounding graphs as the goldens plus the first two
audio-shaped metrics. Ring 2 proper (voice against a real LiveKit room, with
personas and real caller audio) is ms-13; the barge-in stoplist has never
heard a real murmur yet — that test needs your microphone.

Try it (this is the milestone's command):

```bash
uv run python worker.py console --record     # talk to it; Ctrl+T text/audio; Ctrl+C to hang up
uv run python -m convo sessions list
uv run python -m convo sessions show <id>    # tts.word, latencies, the OGG path in session.end
uv run python -m convo sessions eval <id> --voice
uv run python -m core.testing.tts_golden     # the DNI/amount/time A/B, both models
open tmp/reports/ms-6.html                   # the playable recorded call
```

Read it:

```bash
nvim -p core/providers/stt.py core/providers/tts.py core/providers/turn.py core/session.py core/barge_in.py
nvim -p core/observability/voice.py core/testing/speaker.py core/testing/audio.py core/testing/record.py core/testing/tts_golden.py
nvim -p tests/test_voice_events.py tests/test_audio_split.py docs/evals.md
```

## What comes next

**ms-7** — the evaluation ring complete: consent nodes deterministic, the
Thursday-cita prompt defect, the three judge-backed unit tests moved out of
the unit ring, tool result summaries so ring 3 can ground facts, the
simulated caller lifted into core. Then **ms-8**: a LiveKit server locally —
rooms, tokens, dispatch by metadata — the first time the router's metadata
path runs against a real dispatcher.
