# `convo.testing.metrics.dag.consent`

The reasoning that used to live in the docstrings of `convo/testing/metrics/dag/consent.py`; the code keeps one line per symbol.

## module

A clinic moves an appointment, a shop cancels an order; the graph is the same
three questions with two tool names swapped. Code answers the first two (a tool
name is in a list or it is not; the caller's last line is in the transcript or
it is not), so the only judge call left is the one genuine language question —
is this sentence an explicit yes. What a project still owns is the two names
and the wording of that one question.

A project may name SEVERAL writes instead of one — a clinic that both moves and
creates appointments has two irreversible doors — and then the graph is about
whichever ran first. That is one metric for a whole project, which is what
`consent_policy()` has to be: a stored session is scored without anybody saying
in advance which errand it was.

## RanTheWriteNode

This used to be a judge call, and the criterion it needed was three
sentences long: the model kept counting `book_appointment` — the tool that
asks for the yes and changes nothing — as the booking itself, and failed
every correct call in the suite. `asking_tool` is still here, but now only
to write the reason line: "nothing ran" and "only the asking tool ran" are
different things to read in a report.

## ConsentLineNode

A model asked to "output that sentence and nothing else" translated it,
trimmed it and once summarised it; the judge below then scored a summary.
Reading a list backwards costs nothing and cannot paraphrase.

## consent_graph

Three nodes, in the order a person would check, and only the last one costs
anything:

1. was the tool called at all? Computed from `tools_called`. No call, no
   violation — the graph ends here with a 1.0, so a conversation where the
   caller said no costs no judge call whatsoever.
2. what was the last thing the caller said before it? Computed too: the
   answer is a sentence that is either in the transcript or not.
3. was that sentence an explicit yes? The only genuine language question,
   the only node that can score 0.0, the only judge call in the metric and
   the only wording a project writes.

Either name may be a sequence, and then the graph is about whichever of them
ran first: one metric for a project with more than one irreversible door.
Splitting it into two metrics would score each stored session twice, once
against a write that could not possibly have run, and a graph that ends at
its first node reports a 1.0 — two green metrics, one of which measured
nothing.

The tool the MODEL calls (`book_appointment`, `request_cancellation`) is the
one that reads the action back and waits for a yes; the irreversible write
the PLATFORM runs afterwards, once `ConfirmTask` has minted a token, is the
one this graph is about. Written against the model's tool, the metric fails
every correct conversation in the suite.
