# `convo.tools.confirm`

The reasoning that used to live in the docstrings of `convo/tools/confirm.py`; the code keeps one line per symbol.

## module

A token is minted the moment the caller confirms and it authorises exactly one
call: one tool, one set of arguments, once, within a couple of minutes. It is
not a session flag — "the caller confirmed something earlier" is precisely the
ambiguity that books the wrong hour. The guard (`core.tools.guard`) checks it
before an irreversible tool runs; the executor consumes it after.

Open source note: this module is framework-agnostic and copies as-is. A
customer whose confirmations come from a button in an app instead of a spoken
"sí" mints the same token from their own endpoint; the guard does not care
who asked the question.
