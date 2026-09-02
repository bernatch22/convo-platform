# `tenants._template.projects.example.project`

The reasoning that used to live in the docstrings of `tenants/_template/projects/example/project.py`; the code keeps one line per symbol.

## module

A project is everything about ONE thing a caller can ring about: the tools it
may use, the voice it speaks with, its knowledge block, the sentences it says
when a tool fails, and the stage the call starts in. A tenant with two use cases
has two of these folders and one `tenant.py`.

The catalog is data the platform reads before every call, not documentation: a
tool missing from here cannot run, however convincingly the model asks for it,
and the `side_effect` declared on each spec is what decides whether the customer
has to say yes first.

TODO(copy): one `ToolSpec` per capability this use case may reach, the voice,
and the failure sentences in your own register. Declare nothing you have no
adapter for — a tool with no system behind it buys a spoken failure where a
refusal would have been the honest answer.
