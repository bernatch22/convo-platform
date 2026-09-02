# `convo.tools.executor`

The reasoning that used to live in the docstrings of `convo/tools/executor.py`; the code keeps one line per symbol.

## module

The ToolError contract
----------------------
`livekit.agents.llm.ToolError` is the one exception a tool may raise that the
model gets to read: its message is handed back as the tool's output, so it must
be a sentence a caller could hear in the project's language — never a stack
trace, never an internal identifier, never the name of a system. Every other
failure (an undeclared tool, a missing adapter, an adapter blowing up, a
timeout) is translated here into exactly that, and the real cause goes to the
log instead. Which sentence is spoken comes from `core.tools.messages`, so a
project chooses its own register.

This module is the only file in `core/tools` that imports livekit: `contract`,
`guard`, `catalog` and `messages` stay framework-agnostic, so porting the
platform to another agent runtime means rewriting this file alone.

## LocalExecutor

Remote execution (the customer's own code, ms-12) is a second implementation
of `ToolExecutor`; nothing above this line changes when it arrives.

## LocalExecutor._summary

A dict rather than a value so the common case — a tool with no
renderer — adds no key at all and the log of every project that never
opted in is byte-for-byte what it was.

Two things happen before the line is written. The result's own identity
fields are learned as PII first (`_learn_pii` only ever saw the
ARGUMENTS, and `find_patient` is asked for a phone and answers with a
name), so the mask in `record` can blank them; and a renderer that
raises is a bug worth a traceback in the developer log and nothing
else — the call succeeded, the caller is owed their result, and a
missing summary degrades exactly one eval.

## LocalExecutor._learn_pii

Order is the whole point. `send_sms` carries the patient's name inside
`text`, and the only reason we know that string is a name is that some
argument, somewhere, declared it. Learning after masking would leak the
first occurrence of every value — which is the one that matters.

## LocalExecutor._record

`record` scrubs known PII values from whatever this hands it, so a
refusal reason or a timeout note cannot leak a name the arguments
already had masked.

## attach_local_tools

Two steps that only make sense together and only after the context exists
(the executor holds it), so every builder of a TenantContext — the router in
production, the harness in tests — ends with this one line.

One adapter is the PLATFORM's and not the tenant's: `HumanTransfer` reaches
the carrier rather than a customer system, and it is here so that handing a
call to a person is a write like any other — declared in a catalog, vetted
by the guard, timed by its spec and logged twice. It is unreachable for a
project whose catalog does not name `transfer_to_human`, so a tenant that
never opts in is exactly where it was.

## _identity_in

`find_patient` is called with a phone number and comes back with the
patient's full name: a value no argument ever carried, which the mask
therefore did not know and would have written into a summary in the clear.
A list of rows is walked too, since an agenda answering with several
appointments names several people.

## _identity_of

A session knows the patient's name from the moment Identify found them,
before any tool has carried it as an argument. Naming the keys here — and
not reading the whole dict — keeps an appointment id or a doctor out of the
mask, which would blank half of every log line for nothing.
