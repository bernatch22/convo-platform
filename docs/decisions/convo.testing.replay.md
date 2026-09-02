# `convo.testing.replay`

The reasoning that used to live in the docstrings of `convo/testing/replay/__init__.py`; the code keeps one line per symbol.

## module

Rings 1 and 2 build a case from a conversation we just ran and still hold in
memory. Ring 3 has only the append-only log — a list of `Event`s written during
a call that ended hours ago, possibly on another machine — and has to rebuild
the case from that. The metrics do not change: `never_book_before_yes` and
`grounded_facts_dag` are the project's, and they read `turns` and
`tools_called` exactly as they do on a golden.

The conversion is two halves, one file each: `turns.py` decides which turn a
batch of tool events belongs to, `tools.py` pairs those events back into
`ToolCall`s. This module is the door — a session id in, a case out.

**What ring 3 could not see until ms-7.** `tool.result` recorded the SHAPE of a
result (`list[3]`, `str[41]`) and never the payload, because a log that kept
what the agenda returned would keep the patient's hours, doctor and phone next
to their masked name. Consent (`never_book_before_yes`) survived that — it
reads tool NAMES, and `book_slot` is in the log because the platform ran it —
but grounding could not: a claim that came off the agenda reached the judge
with evidence that could not contain it, and every real session scored 0.0 on
the metric's own blindness.

A tool now declares a `result_summary` on its `ToolSpec` (`core/tools/contract.py`):
the executor renders the result through it, the session's PII mask blanks
whatever the renderer let through, and the line is written as `summary` on
`tool.result`. `tools.py` puts it into `ToolCall.output` and grounding's
`evidence_of` reads it like any other tool output. A tool that declares no
renderer is unchanged and `missing_tool_outputs` still names it, so the CLI
keeps saying which scores must not be read as inventions. `docs/evals.md` §3.6.

Open source note: nothing below knows about clinics or about LiveKit. It reads
a `Store` and returns DeepEval objects, so any project whose log speaks these
kinds gets ring 3 for free.

## conversational_case_from

`descriptions` is the project's tool contracts by name (`descriptions_for`),
so a judge shown a call also sees what that tool was for. No
`expected_outcome`: a real call is not a golden, nobody wrote down what it
was supposed to do, and inventing one here would be the eval marking its own
homework.

## descriptions_for

A stored session has a tenant and a project on its row but no live context,
so one is built offline exactly as the test harness builds one — the
adapters are never called, only the stages' docstrings are read.
