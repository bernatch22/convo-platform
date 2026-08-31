"""Overrides: the console's edits on top of the project git deployed.

A supervisor changes a voice, a TTS model or the opening line between two
calls; a deploy is the wrong unit for that. The row lives in the store
(`pipeline_overrides`) and this module is where it becomes a `Project` again:
`resolve` calls `apply` once, so every session — voice, chat, console — starts
from the same overridden object and nothing downstream knows a row was
involved.

Only the three fields in `OVERRIDABLE` can be set this way. A value the
platform refuses to run is still refused where it is built: an override naming
a forbidden TTS model is neutralised by `core.providers.tts.tts_model`, and the
control plane refuses to store one in the first place.
"""

import dataclasses

from core.context import Project
from core.state.store import Store

OVERRIDABLE = ("voice", "tts_model", "greeting", "llm_model")


def apply(tenant: str, project: Project, store: Store) -> Project:
    """The project as the console leaves it: a copy with every stored override replaced.

    Returns the project untouched when there is no row for it, so a deploy with
    an empty table behaves exactly as it did before the table existed.
    """
    edits = {o.field: o.value for o in store.pipeline_overrides(tenant, project.id)}
    edits = {name: value for name, value in edits.items() if name in OVERRIDABLE}
    return dataclasses.replace(project, **edits) if edits else project
