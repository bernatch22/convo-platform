# `convo.observability.observers`

The reasoning that used to live in the docstrings of `convo/observability/observers.py`; the code keeps one line per symbol.

## module

The framework already emits everything an audit needs — a turn with its
latencies, a final transcript, the agent's state, the batch of tools that ran,
an error, the close and its reason. This module is the one place that knows
those names, so the log keeps its own vocabulary (`turn.agent`, `stt.final`,
`session.end`) and swapping the runtime is a change to this file alone.

What it deliberately does NOT do: log each tool call. The executor already
writes `tool.call` / `tool.result` with the arguments masked by `pii_scope`,
and it is the only place that knows which argument is a DNI. Here a batch of
tools is one line with a count, never the arguments again.

Every handler is synchronous and swallows nothing: LiveKit's emitter calls
them inline, so a slow or raising observer would sit in the audio path. They
do one dict and one append each.

Open source note: `observe(session, tc)` needs only `tc.log`; a fork that
keeps its events elsewhere replaces `EventLog` and nothing here changes.

## turn_metrics

`MetricsReport` is a total=False TypedDict, so which keys exist depends on
the turn: a text-only session has no `tts_node_ttfb`, a greeting nobody was
asked for has no `e2e_latency`. Asserting on the shape would be asserting
on the modality.
