# `convo.domain.catalog`

The reasoning that used to live in the docstrings of `convo/domain/catalog.py`; the code keeps one line per symbol.

## module

A catalog is data, not behaviour: the executor looks a name up here before it
guards, times or runs anything. A project that does not declare a tool cannot
call it, however convincing the model is about wanting to.

Two catalogs come from the platform and they are not the same thing.
`platform_specs()` is what a project INHERITS and may merge into its own: real
tools, run by the executor against the tenant's adapters. `infrastructure_specs()`
is the platform's own plumbing — the clock every `TenantAgent` carries — which
no project declares, no adapter backs and the executor never sees, because
livekit runs it as a plain `@function_tool` on the agent. It is declared here
anyway, and marked `infrastructure=True`, so that everything downstream can ask
a tool whether it belongs to the business instead of matching its name.

## infrastructure_specs

Deliberately NOT merged into `platform_specs()`. A project's catalog is the
list of names the executor will accept, and the clock never reaches the
executor — putting it there would promise a call the platform cannot route.

## infrastructure_names

Derived from the flag, never from a list of names written somewhere else:
a project that adds plumbing of its own marks the spec and this answer grows
with it. Callers that only care about the platform's pass nothing.
