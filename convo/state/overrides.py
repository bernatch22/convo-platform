"""Overrides: the console's edits on top of the project git deployed.

A supervisor changes a voice, a TTS model or the opening line between two
calls; a deploy is the wrong unit for that. The row lives in the store
(`pipeline_overrides`) and this module is where it becomes a `Project` again:
`resolve` calls `apply` once, so every session — voice, chat, console — starts
from the same overridden object and nothing downstream knows a row was
involved.

Only the fields in `OVERRIDABLE` can be set this way. A value the platform
refuses to run is still refused where it is built: an override naming a
forbidden TTS model is neutralised by `core.providers.tts.tts_model` and one
naming an STT provider we do not have by `core.providers.stt.provider_for`,
and the control plane refuses to store either in the first place.
"""

import dataclasses

from convo.domain.context import Project
from convo.state.store import Store

OVERRIDABLE = (
    "voice",
    "tts_model",
    "greeting",
    "stt_provider",
    "llm_model",
    "transfer_number",
)

# The two fields whose empty value MEANS something. No greeting: the entry
# stage's prompt opens the call. No transfer_number: the agent is offered no
# transfer verb at all, which is how the console TAKES the verb away — so an
# empty row has to reach the project, not be ignored as noise. Everywhere else
# "" is a value nobody chose — an empty voice builds no TTS and the call is
# mute — so a blank row is ignored here as well as refused by
# `core.pipeline.overridable`, and a project stored empty before that rule
# existed cannot silence a call after this deploy.
BLANKABLE = ("greeting", "transfer_number")


def apply(tenant: str, project: Project, store: Store) -> Project:
    """The project as the console leaves it: a copy with every stored override replaced.

    Returns the project untouched when there is no row for it, so a deploy with
    an empty table behaves exactly as it did before the table existed.
    """
    edits = {o.field: o.value for o in store.pipeline_overrides(tenant, project.id)}
    edits = {name: value for name, value in edits.items() if _applies(name, value)}
    return dataclasses.replace(project, **edits) if edits else project


def _applies(field: str, value: str) -> bool:
    """Whether this stored row is a value the platform should really run."""
    return field in OVERRIDABLE and (bool(value) or field in BLANKABLE)
