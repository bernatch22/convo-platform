# `convo.tools.guard`

The reasoning that used to live in the docstrings of `convo/tools/guard.py`; the code keeps one line per symbol.

## module

Framework-agnostic on purpose: `check` and `mask` take a `ToolSpec` and a plain
dict, so any agent runtime can reuse them. `check` is the single place that
decides whether a call may happen at all — the executor never second-guesses it.

The mask has two halves. By NAME: an argument a `ToolSpec` lists in `pii_scope`
never reaches a log intact. By VALUE: the values those arguments carried are
remembered on the session (`TenantContext.pii_values`) and blanked wherever
they turn up again — inside an SMS body, a question, a reason. Both halves are
driven by what a ToolSpec declared; there is no global regex hunting for names
in this platform, and there never should be.

## check

Two rules: a spec must declare a positive timeout, and an irreversible tool
must carry a confirmation token minted for exactly this call, still fresh
and not yet spent. Refusing is not an error the LLM sees; the calling stage
decides what to say (it asks for confirmation).

## mask

Two characters survive so a human reading a log can still tell two values
apart; everything a person could be identified by is gone.

Masking by argument NAME is not enough on its own: `send_sms` declares
`pii_scope={"phone"}` and puts the patient's name in the middle of `text`,
which the contract says nothing about. So every value in `known` — the
session's PII, collected from the `pii_scope` arguments seen so far — is
masked wherever it appears inside any other string argument too. Still no
global regex: a value is PII here only because some ToolSpec said so.

## scrub

What the seams use. A stage, a confirmation or a saga hands `record` a
payload no ToolSpec describes — a question, a step name, a reason — and
this is the one pass that keeps a name the caller gave us out of it.
Recursive, so an already-masked `args` dict nested inside is simply
unchanged (a masked value no longer contains the value).

## learn

Short values are dropped on purpose: a two-character pattern would blank
half of every sentence in the log, and `xx****` of it says nothing anyway.
