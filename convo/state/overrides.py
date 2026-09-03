"""Overrides: the console's edits on top of the project git deployed.

Decisions: docs/decisions/convo.state.overrides.md
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
# `convo.session.pipeline.overridable`, and a project stored empty before that rule
# existed cannot silence a call after this deploy.
BLANKABLE = ("greeting", "transfer_number")


def apply(tenant: str, project: Project, store: Store) -> Project:
    """The project as the console leaves it: a copy with every stored override replaced."""
    edits = {o.field: o.value for o in store.pipeline_overrides(tenant, project.id)}
    edits = {name: value for name, value in edits.items() if _applies(name, value)}
    return dataclasses.replace(project, **edits) if edits else project


def _applies(field: str, value: str) -> bool:
    """Whether this stored row is a value the platform should really run."""
    return field in OVERRIDABLE and (bool(value) or field in BLANKABLE)
