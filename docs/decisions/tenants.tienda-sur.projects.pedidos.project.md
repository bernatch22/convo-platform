# `tenants.tienda-sur.projects.pedidos.project`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/projects/pedidos/project.py`; the code keeps one line per symbol.

## module

The shop's half of ms-5. Same runtime as the clinic, same stages-and-saga
shape, and every single thing that differs is data in this folder: the tools
below, the knowledge block, the prompts, the voice, the failure sentences and
the register — a shop says "tú".

The catalog is the whole of what this project may call. It is data the platform
reads before every call, not documentation: a tool missing from here cannot
run, however convincingly the model asks for it, and the side effect declared
on each spec is what decides whether a customer has to say yes first.

`platform_specs()` is deliberately not merged in. The platform's inherited
catalog still carries `find_availability` from ms-2, an agenda tool this shop
has no system for; declaring a tool no adapter can serve buys a project a
spoken failure instead of a refusal, and the refusal is the honest answer.
