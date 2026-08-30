"""Shapes that cross a process boundary (dispatch metadata, control-plane payloads)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Channel = Literal["voice", "chat"]


class SessionMeta(BaseModel):
    """What the dispatcher (JWT or SIP rule) tells the worker about a session.

    Unknown fields are ignored on purpose: an older worker must keep starting
    against a newer control plane.
    """

    model_config = ConfigDict(extra="ignore")

    tenant: str
    project: str
    channel: Channel = "voice"
    project_version: str | None = None
