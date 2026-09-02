# `convo.domain.tools`

The reasoning that used to live in the docstrings of `convo/domain/tools.py`; the code keeps one line per symbol.

## module

`result_summary` is the newest clause and the one with a story. The session log
records the SHAPE of a result (`list[3]`) and never its payload, because a log
that kept what an agenda returned would keep a patient's hours and doctor next
to their masked name. That rule is right for a raw result and wrong for the
whole result: an auditor reading the log — and ring 3's grounding metric
reading it as evidence — needs to know that the hours the agent read out came
off the agenda and were not invented. So a tool may declare ONE function that
renders its own result into a short line the log may keep. It is opt-in per
tool, written by the project that knows which fields are safe, and everything
it produces still goes through the session's PII mask before it is written.

`infrastructure` is the second opt-in clause, and it says the opposite thing
about a tool: this one is not the business's. The clock every agent inherits
answers "what day is it" and touches nothing a customer owns, so an eval that
asks "did the turn call the agenda when it should" must not count it — a golden
that expects no BUSINESS call is not a golden that expects silence. The flag is
declared here rather than guessed by name so a project can mark its own
plumbing too, and so nothing anywhere holds a list of tool names to skip.

## ToolSpec.is_business_tool

The one question an eval about `expected_tools` asks of a call. A
golden lists the tools of the BUSINESS, so the clock the platform puts
on every agent has to be able to say it is not one of them.

## ToolSpec.summarise

Not the place PII is removed: a renderer chooses which FIELDS are worth
keeping, and the session's mask blanks the values inside them
afterwards. Both halves are needed — a renderer that never names the
patient is still handed a doctor's note if the adapter puts one in the
field it reads.

Exceptions travel: a renderer given a shape it did not expect is a bug
in the project, and the executor is the layer that decides a bug in a
log line must never fail a tool call that already succeeded.
