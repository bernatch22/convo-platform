"""Serve the built React app (`ui/dist`) from the control plane, when it has been built.

Decisions: docs/decisions/convo.api.webui.md
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_DIST = REPO_ROOT / "ui" / "dist"


def mount_ui(app: FastAPI, dist: Path = UI_DIST) -> bool:
    """Serve `dist` at / with SPA fallback; False (and no route added) when it is not built."""
    index = dist / "index.html"
    if not index.is_file():
        return False

    root = dist.resolve()

    @app.get("/{asset_path:path}", include_in_schema=False)
    def ui(asset_path: str) -> FileResponse:
        """Any path the API did not claim: the real file if there is one, else the SPA shell."""
        return FileResponse(_resolve(root, asset_path) or index)

    return True


def _resolve(root: Path, asset_path: str) -> Path | None:
    """The real file this path names inside `root`, or None (missing, or an escape attempt)."""
    if not asset_path:
        return None
    candidate = (root / asset_path).resolve()
    if root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None
