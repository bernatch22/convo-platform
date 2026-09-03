# `convo.adapters.base`

The reasoning that used to live in the docstrings of `convo/adapters/base.py`; the code keeps one line per symbol.

## module

One capability name in here is not a tool: `LIST_RECORDS` is the read the
OPERATOR CONSOLE asks an adapter for, never something a model may call. It
exists because the console's first question — show me the reservations, who,
when, with whom, in what state — is a question about the BUSINESS system and
not about the platform. The event log answers what the platform did, with its
summaries PII-filtered by design; the reservation itself, with the patient's
name on it, lives where it has always lived, and this is the door to it.

Nothing in `convo/` knows what an adapter's records are called. The adapter
answers with its own SHAPE, its own column labels and its own state words, and
the console renders whatever came back — so a clinic answers with appointments,
a shop answers with orders, and a tenant whose systems have no such view
answers nothing at all and the console says so plainly.
