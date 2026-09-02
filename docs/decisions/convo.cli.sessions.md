# `convo.cli.sessions`

The reasoning that used to live in the docstrings of `convo/cli/sessions.py`; the code keeps one line per symbol.

## tail_session

Watching the pipeline breathe in the terminal: when the stt.final arrives,
when the state flips listening→thinking→speaking, when the first tts word
leaves, and each turn's ttft/e2e chips. With no id it waits for the newest
session — start it, then call the number. Ctrl+C ends it.

## eval_session

The same metrics the CI suite runs on goldens, on a call that really
happened: the log becomes a `ConversationalTestCase` and each metric prints
its score, its threshold and why. What the replay could not see is printed
with the score that suffers from it, never left for the reader to work out.

## score_voice

They are detectors, not judges: `AudioIntegrityMetric` measures the agent's
own audio (clipping, dropouts, loops, an abrupt cutoff) and
`AgentResponsivenessMetric` reads the shape of the turns and whether every
answer arrived with sound. Neither calls a model, so this costs nothing and
needs no key — only the OGG the session recorded.

## score_session

The same function the control plane's sweeper runs, called by hand: the
four deterministic checks, then at most one judged metric under its cap.
`--free` runs the deterministic half alone and spends nothing. Asking twice
is safe — the second call prints the score the first one wrote, because
`session.score` is a log line and the log is append-only.

## _explanation

DeepEval's verbose log is the whole graph: every criterion, every rendered
block, the clinic's information sheet in full. An operator asking why a call
scored 0.0 wants the labels and the one-line reason each node wrote, so that
is what is kept and the rest is left for `deepeval test run -v`.
