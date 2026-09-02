# `convo.testing.replay.turns`

The reasoning that used to live in the docstrings of `convo/testing/replay/turns.py`; the code keeps one line per symbol.

## module

The turns are `turn.user` and `turn.agent` in seq order, and the tool events
between two agent turns hang from the **following** assistant turn: Haiku says
"un momento, le consulto la agenda", the tools run, and the answer is what they
produced. Pairing those tool events into calls is `tools.py`; this module only
decides which turn each batch belongs to.

Pure and model-free: hand `turns_from` a list of events and it hands back
turns, which is how the conversion is tested without spending a cent.

## _attach_trailing

A booking whose SMS went out while the agent was already hanging up, or a
session killed after its last reply, leaves tool events with no turn after
them. They go on the last assistant turn — and if the call has no assistant
turn at all, on a silent one, because dropping them would hide the only
record that the customer's system was written to.
