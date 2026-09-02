"""Where a call's audio lives, who may hear it, and how a job is aimed at it.

Decisions: docs/decisions/convo.session.recordings.md
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("platform.recordings")

ROOT_ENV = "CONVO_RECORDINGS"
DEFAULT_ROOT = "tmp/recordings"
TOKEN_ENV = "RECORDINGS_TOKEN"
FILENAME = "audio.ogg"
MEDIA_TYPE = "audio/ogg"

# A session id is ours (`ctx.job.id`, `rec-<hex>`, a test's literal), never a
# caller's text — but it arrives at the read side as a URL segment, so it is
# checked before it is ever joined to a path. No dots, so no traversal exists
# to defend against in the first place.
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def root() -> Path:
    """The directory every recording lives under: `CONVO_RECORDINGS`, else `tmp/recordings`."""
    return Path(os.getenv(ROOT_ENV, DEFAULT_ROOT))


def path_for(session_id: str) -> Path:
    """Where THIS session's OGG belongs — `<root>/<session_id>/audio.ogg`, created or not."""
    return root() / session_id / FILENAME


def for_session(session_id: str) -> Path | None:
    """The recording of a session that has one, or None — the read side's only lookup."""
    if not SAFE_ID.match(session_id):
        return None
    path = path_for(session_id)
    return path if path.is_file() else None


def keep(project: Any) -> bool:
    """Whether this project's calls keep their audio; a project may opt out of being recorded."""
    return bool(getattr(project, "recording", True))


def aim(ctx: Any, session_id: str) -> Path | None:
    """Point this job's recorder at `<root>/<session_id>/audio.ogg`; the path, or None."""
    path = path_for(session_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        ctx._session_directory = path.parent
    except Exception:
        log.exception("cannot aim the recorder at %s; this call keeps no audio", path)
        return None
    return path


def authorised(presented: str | None) -> bool:
    """Whether a request may hear a recording: true unless `RECORDINGS_TOKEN` says otherwise."""
    expected = os.getenv(TOKEN_ENV, "")
    return not expected or presented == expected
